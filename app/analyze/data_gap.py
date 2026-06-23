from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

DATA_NODE_DAILY_PRICE = "daily_price"
DATA_NODE_INSTITUTIONAL = "institutional"

STATUS_CURRENT = "current"
STATUS_GAP = "gap"
STATUS_SOURCE_PENDING = "source_pending"
STATUS_PATCHED = "patched"
STATUS_SUSPECT = "suspect"
STATUS_FORCE_REFRESH_REQUIRED = "force_refresh_required"


@dataclass(frozen=True, slots=True)
class DataGapPlan:
    stock_id: str
    node: str
    status: str
    local_latest_date: date | None
    target_date: date | None
    fetch_start_date: date | None
    fetch_end_date: date | None
    gap_business_days: int
    can_patch: bool
    force_refresh_required: bool
    reason: str

    def to_json(self) -> dict[str, object]:
        return {
            "stock_id": self.stock_id,
            "node": self.node,
            "status": self.status,
            "local_latest_date": _date_json(self.local_latest_date),
            "target_date": _date_json(self.target_date),
            "fetch_start_date": _date_json(self.fetch_start_date),
            "fetch_end_date": _date_json(self.fetch_end_date),
            "gap_business_days": self.gap_business_days,
            "can_patch": self.can_patch,
            "force_refresh_required": self.force_refresh_required,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PostPatchStatus:
    status: str
    reason: str

    def to_json(self) -> dict[str, object]:
        return {"status": self.status, "reason": self.reason}


def plan_data_gap(
    *,
    stock_id: str,
    node: str,
    coverage: dict[str, Any] | None,
    target_date: date | str | None,
    lookback_days: int,
    max_patch_business_days: int = 45,
) -> DataGapPlan:
    """Decide whether a data node is current or needs a bounded patch request."""
    sid = stock_id.strip()
    if not sid:
        raise ValueError("stock_id is required")
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")

    target = _as_date(target_date)
    latest = _as_date((coverage or {}).get("latest_date"))
    if target is None:
        return DataGapPlan(
            stock_id=sid,
            node=node,
            status=STATUS_SOURCE_PENDING,
            local_latest_date=latest,
            target_date=None,
            fetch_start_date=None,
            fetch_end_date=None,
            gap_business_days=0,
            can_patch=False,
            force_refresh_required=False,
            reason="No target date is available for this source yet.",
        )

    if latest is not None and latest >= target:
        return DataGapPlan(
            stock_id=sid,
            node=node,
            status=STATUS_CURRENT,
            local_latest_date=latest,
            target_date=target,
            fetch_start_date=None,
            fetch_end_date=None,
            gap_business_days=0,
            can_patch=False,
            force_refresh_required=False,
            reason=f"{node} is current through {target.isoformat()}.",
        )

    if latest is None:
        fetch_start = target - timedelta(days=lookback_days)
        gap_days = count_business_days(fetch_start, target)
        return DataGapPlan(
            stock_id=sid,
            node=node,
            status=STATUS_GAP,
            local_latest_date=None,
            target_date=target,
            fetch_start_date=fetch_start,
            fetch_end_date=target,
            gap_business_days=gap_days,
            can_patch=True,
            force_refresh_required=False,
            reason=f"No local {node} coverage; initial backfill is required.",
        )

    fetch_start = latest + timedelta(days=1)
    gap_days = count_business_days(fetch_start, target)
    if gap_days > max_patch_business_days:
        wide_start = target - timedelta(days=lookback_days)
        return DataGapPlan(
            stock_id=sid,
            node=node,
            status=STATUS_FORCE_REFRESH_REQUIRED,
            local_latest_date=latest,
            target_date=target,
            fetch_start_date=wide_start,
            fetch_end_date=target,
            gap_business_days=gap_days,
            can_patch=False,
            force_refresh_required=True,
            reason=(
                f"{node} gap has {gap_days} business day(s), above the "
                f"{max_patch_business_days}-day patch gate."
            ),
        )

    return DataGapPlan(
        stock_id=sid,
        node=node,
        status=STATUS_GAP,
        local_latest_date=latest,
        target_date=target,
        fetch_start_date=fetch_start,
        fetch_end_date=target,
        gap_business_days=gap_days,
        can_patch=True,
        force_refresh_required=False,
        reason=f"{node} is missing {gap_days} business day(s).",
    )


def resolve_post_patch_status(
    plan: DataGapPlan,
    *,
    latest_date: date | str | None,
    rows_written: int,
) -> PostPatchStatus:
    latest = _as_date(latest_date)
    if plan.target_date is None:
        return PostPatchStatus(STATUS_SOURCE_PENDING, "No target date was available.")
    if latest is not None and latest >= plan.target_date:
        if plan.status == STATUS_CURRENT:
            return PostPatchStatus(STATUS_CURRENT, "Coverage was already current.")
        return PostPatchStatus(STATUS_PATCHED, "Coverage reached the target date after patching.")
    if rows_written <= 0:
        return PostPatchStatus(
            STATUS_SOURCE_PENDING,
            "The source returned no newer rows; it may not have published the target date yet.",
        )
    return PostPatchStatus(
        STATUS_SUSPECT,
        "Rows were written but coverage still did not reach the target date.",
    )


def count_business_days(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        return 0
    total = 0
    day = start_date
    while day <= end_date:
        if day.weekday() < 5:
            total += 1
        day += timedelta(days=1)
    return total


def previous_business_day(day: date) -> date:
    current = day
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _date_json(value: date | None) -> str | None:
    return value.isoformat() if value else None
