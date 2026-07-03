from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.analyze.twse_calendar import (
    count_twse_trading_days,
    next_twse_trading_day,
    previous_twse_trading_day,
)

DATA_NODE_DAILY_PRICE = "daily_price"
DATA_NODE_INSTITUTIONAL = "institutional"

STATUS_CURRENT = "current"
STATUS_GAP = "gap"
STATUS_SOURCE_PENDING = "source_pending"
STATUS_PATCHED = "patched"
STATUS_SUSPECT = "suspect"
STATUS_FORCE_REFRESH_REQUIRED = "force_refresh_required"

# ---- depth（歷史完整度）：與 freshness（最新度）分離的第二軸 ----
# 背景：STOCK_DAY_ALL top-up 只寫「最新一日」，latest_date 到位不代表歷史存在。
# 舊的 row_count <= 5 常數門檻有兩個漏洞：
#   (a) 受災股被每日 top-up 累積超過 5 筆後又被判 current，歷史永遠補不回；
#   (b) 真・新上市股永遠 <= 5 筆，每次都被強制重抓 13 個月（幾乎全空）。
# 因此深度改為「期望筆數」推導：期望 = max(上市日, target-一年) 到 target 的交易日數。
# STOCK_DAY_ALL 因此天生只能推高 freshness、推不動 depth，不需特殊標記。
DEPTH_HORIZON_CALENDAR_DAYS = 365  # 產品口徑：近一年日線即算完整（與 bulk lookback 對齊）
DEPTH_USABLE_RATIO = 0.5  # 低於此比例 → 需要歷史回補（寬鬆以容忍停牌／處置造成的缺洞）
DEPTH_DEEP_RATIO = 0.9
DEPTH_LATEST_ONLY_MAX_SPAN_BUSINESS_DAYS = 7  # earliest 距 target 很近 → 只有最新幾筆

DEPTH_EMPTY = "empty"
DEPTH_LATEST_ONLY = "latest_only"
DEPTH_SHALLOW = "shallow"
DEPTH_USABLE = "usable"
DEPTH_DEEP = "deep"


@dataclass(frozen=True, slots=True)
class DepthAssessment:
    """日線歷史完整度（不看 latest 是否到位，那是 freshness 的事）。"""

    level: str
    row_count: int
    expected_days: int
    ratio: float
    horizon_start: date | None

    @property
    def needs_backfill(self) -> bool:
        return self.level in (DEPTH_EMPTY, DEPTH_LATEST_ONLY, DEPTH_SHALLOW)

    def to_json(self) -> dict[str, object]:
        return {
            "level": self.level,
            "row_count": self.row_count,
            "expected_days": self.expected_days,
            "ratio": self.ratio,
            "horizon_start": _date_json(self.horizon_start),
            "needs_backfill": self.needs_backfill,
        }


def depth_horizon_start(
    target_date: date,
    *,
    listed_date: date | str | None = None,
    horizon_days: int = DEPTH_HORIZON_CALENDAR_DAYS,
) -> date:
    """深度視窗起點＝抓取起點：max(上市日, target - 一年)。新上市股不再空抓 13 個月。"""
    start = target_date - timedelta(days=max(1, horizon_days))
    listed = _as_date(listed_date)
    if listed is not None and listed > start:
        start = listed
    return start


def assess_daily_depth(
    *,
    coverage: dict[str, Any] | None,
    target_date: date | str | None,
    listed_date: date | str | None = None,
    horizon_days: int = DEPTH_HORIZON_CALENDAR_DAYS,
) -> DepthAssessment:
    """row_count 對比「視窗內應有的交易日數」推導深度等級。

    注意 expected 一定從 horizon_start 起算，不能從 earliest 起算——
    top-up-only 的股票 earliest≈latest，用 earliest 起算會自我安慰成 deep。
    """
    target = _as_date(target_date)
    raw_row_count = _int_or_none((coverage or {}).get("horizon_row_count"))
    if raw_row_count is None:
        raw_row_count = _int_or_none((coverage or {}).get("row_count"))
    row_count = raw_row_count or 0
    earliest = _as_date((coverage or {}).get("earliest_date"))
    latest = _as_date((coverage or {}).get("latest_date"))
    if target is None:
        # 沒有目標日就無法評深度；不擋路，交給 source_pending 流程。
        return DepthAssessment(DEPTH_DEEP, row_count, 0, 1.0, None)
    start = depth_horizon_start(target, listed_date=listed_date, horizon_days=horizon_days)
    expected = max(1, count_business_days(start, target))
    if raw_row_count is None and latest is not None:
        # coverage 沒帶 row_count 的極簡輸入：有 latest 代表確實有資料，
        # 深度未知時不強制回補（真實 store 的 coverage 一律帶 row_count）。
        return DepthAssessment(DEPTH_DEEP, 0, expected, 1.0, start)
    if row_count <= 0:
        return DepthAssessment(DEPTH_EMPTY, 0, expected, 0.0, start)
    ratio = min(1.0, row_count / expected)
    if ratio >= DEPTH_DEEP_RATIO:
        level = DEPTH_DEEP
    elif ratio >= DEPTH_USABLE_RATIO:
        level = DEPTH_USABLE
    elif (
        earliest is not None
        and count_business_days(earliest, target) <= DEPTH_LATEST_ONLY_MAX_SPAN_BUSINESS_DAYS
    ):
        level = DEPTH_LATEST_ONLY
    else:
        level = DEPTH_SHALLOW
    return DepthAssessment(level, row_count, expected, round(ratio, 4), start)


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
    depth: DepthAssessment | None = None

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
            "depth": self.depth.to_json() if self.depth is not None else None,
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
    listed_date: date | str | None = None,
) -> DataGapPlan:
    """Decide whether a data node is current or needs a bounded patch request.

    daily_price 節點同時看兩軸：freshness（latest vs target）與 depth（歷史完整度）。
    最新到位但歷史不足 → force_refresh_required（歷史回補），修掉「STOCK_DAY_ALL
    先補最新 1~2 天被誤判已完成」這一類問題。listed_date 用來推導期望深度並收斂
    抓取窗口（新上市股從上市日抓起，不再空抓一年）。
    """
    sid = stock_id.strip()
    if not sid:
        raise ValueError("stock_id is required")
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")

    target = _as_date(target_date)
    latest = _as_date((coverage or {}).get("latest_date"))
    depth: DepthAssessment | None = None
    if node == DATA_NODE_DAILY_PRICE:
        depth = assess_daily_depth(
            coverage=coverage,
            target_date=target,
            listed_date=listed_date,
        )
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
            depth=depth,
        )

    if (
        node == DATA_NODE_DAILY_PRICE
        and latest is not None
        and latest >= target
        and depth is not None
        and depth.needs_backfill
    ):
        # 最新到位（多半來自 STOCK_DAY_ALL top-up）但歷史深度不足 → 回補歷史。
        # 窗口 = depth 視窗（上市日 clamp 過），不用 caller 的 lookback（api 端是 5 年）。
        fetch_start = depth.horizon_start or (target - timedelta(days=lookback_days))
        gap_days = count_business_days(fetch_start, target)
        return DataGapPlan(
            stock_id=sid,
            node=node,
            status=STATUS_FORCE_REFRESH_REQUIRED,
            local_latest_date=latest,
            target_date=target,
            fetch_start_date=fetch_start,
            fetch_end_date=target,
            gap_business_days=gap_days,
            can_patch=False,
            force_refresh_required=True,
            reason=(
                f"{node} is {depth.level}: only {depth.row_count} row(s) but about "
                f"{depth.expected_days} trading day(s) are expected since "
                f"{fetch_start.isoformat()}; historical backfill is required."
            ),
            depth=depth,
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
            depth=depth,
        )

    if latest is None:
        fetch_start = _clamped_lookback_start(target, lookback_days, listed_date)
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
            depth=depth,
        )

    fetch_start = next_business_day(latest + timedelta(days=1))
    gap_days = count_business_days(fetch_start, target)
    if gap_days > max_patch_business_days:
        wide_start = _clamped_lookback_start(target, lookback_days, listed_date)
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
            depth=depth,
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
        depth=depth,
    )


def _clamped_lookback_start(
    target: date,
    lookback_days: int,
    listed_date: date | str | None,
) -> date:
    """回補起點不早於上市日（有給才 clamp；查不到上市日則維持原行為）。"""
    start = target - timedelta(days=lookback_days)
    listed = _as_date(listed_date)
    if listed is not None and start < listed <= target:
        return listed
    return start


def resolve_post_patch_status(
    plan: DataGapPlan,
    *,
    latest_date: date | str | None,
    rows_written: int,
    source_pending_grace_business_days: int = 1,
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
    if latest is not None:
        lag_days = count_business_days(latest + timedelta(days=1), plan.target_date)
        if 0 < lag_days <= source_pending_grace_business_days:
            return PostPatchStatus(
                STATUS_SOURCE_PENDING,
                "Rows were written, but the source is still within the publication grace window.",
            )
    return PostPatchStatus(
        STATUS_SUSPECT,
        "Rows were written but coverage still did not reach the target date.",
    )


def market_node_freshness(
    latest_date: date | str | None,
    target_date: date | str | None,
    *,
    grace_business_days: int = 1,
) -> dict[str, object]:
    """Assess freshness for market-wide nodes such as institutional T86."""
    latest = _as_date(latest_date)
    target = _as_date(target_date)
    if target is None:
        return {
            "status": STATUS_SOURCE_PENDING,
            "gap_business_days": 0,
            "latest_date": _date_json(latest),
        }
    if latest is None:
        return {
            "status": "missing",
            "gap_business_days": 0,
            "latest_date": None,
        }
    if latest >= target:
        return {
            "status": STATUS_CURRENT,
            "gap_business_days": 0,
            "latest_date": _date_json(latest),
        }
    gap_days = count_business_days(latest + timedelta(days=1), target)
    return {
        "status": STATUS_CURRENT if gap_days <= grace_business_days else STATUS_GAP,
        "gap_business_days": gap_days,
        "latest_date": _date_json(latest),
    }


def count_business_days(start_date: date, end_date: date) -> int:
    return count_twse_trading_days(start_date, end_date)


def previous_business_day(day: date) -> date:
    return previous_twse_trading_day(day)


def next_business_day(day: date) -> date:
    return next_twse_trading_day(day)


def same_month_tail_date(fetch_end_date: date, max_end_date: date) -> date:
    """Return a same-month tail date without expanding the TWSE month range."""
    if max_end_date <= fetch_end_date:
        return fetch_end_date
    month_end = date(
        fetch_end_date.year,
        fetch_end_date.month,
        monthrange(fetch_end_date.year, fetch_end_date.month)[1],
    )
    return min(max_end_date, month_end)


def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _date_json(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
