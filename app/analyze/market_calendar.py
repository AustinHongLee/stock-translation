from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.analyze.data_gap import count_business_days, previous_business_day


@dataclass(frozen=True, slots=True)
class MarketTargetDate:
    target_date: date
    reference_date: date | None
    market_latest_date: date | None
    snapshot_checked_date: date | None
    expected_latest_close_date: date
    source: str
    snapshot_lag_business_days: int
    snapshot_checked_lag_business_days: int
    snapshot_stale: bool

    def to_json(self) -> dict[str, object]:
        return {
            "target_date": self.target_date.isoformat(),
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "market_latest_date": self.market_latest_date.isoformat() if self.market_latest_date else None,
            "snapshot_checked_date": self.snapshot_checked_date.isoformat() if self.snapshot_checked_date else None,
            "expected_latest_close_date": self.expected_latest_close_date.isoformat(),
            "source": self.source,
            "snapshot_lag_business_days": self.snapshot_lag_business_days,
            "snapshot_checked_lag_business_days": self.snapshot_checked_lag_business_days,
            "snapshot_stale": self.snapshot_stale,
        }


def previous_completed_business_day(as_of: date) -> date:
    return previous_business_day(as_of - timedelta(days=1))


def resolve_market_target_date(
    *,
    reference_date: date | None,
    market_latest_date: date | None = None,
    snapshot_checked_date: date | None = None,
    as_of: date | None = None,
    tolerated_snapshot_lag_business_days: int = 1,
) -> MarketTargetDate:
    today = as_of or date.today()
    expected = previous_completed_business_day(today)
    snapshot_date = reference_date or market_latest_date
    if snapshot_date is None:
        return MarketTargetDate(
            target_date=expected,
            reference_date=None,
            market_latest_date=None,
            snapshot_checked_date=snapshot_checked_date,
            expected_latest_close_date=expected,
            source="calendar_fallback",
            snapshot_lag_business_days=0,
            snapshot_checked_lag_business_days=_business_lag(snapshot_checked_date, expected),
            snapshot_stale=True,
        )

    lag = _business_lag(snapshot_date, expected)
    checked_lag = _business_lag(snapshot_checked_date, expected) if snapshot_checked_date else lag
    snapshot_stale = (
        lag > tolerated_snapshot_lag_business_days
        and checked_lag > tolerated_snapshot_lag_business_days
    )
    if snapshot_stale:
        target_date = expected
        source = "calendar_fallback"
    else:
        target_date = snapshot_date
        source = "stock_snapshot" if reference_date else "market_snapshot"
    return MarketTargetDate(
        target_date=target_date,
        reference_date=reference_date,
        market_latest_date=market_latest_date,
        snapshot_checked_date=snapshot_checked_date,
        expected_latest_close_date=expected,
        source=source,
        snapshot_lag_business_days=lag,
        snapshot_checked_lag_business_days=checked_lag,
        snapshot_stale=snapshot_stale,
    )


def _business_lag(snapshot_date: date | None, expected_date: date) -> int:
    if snapshot_date is None or snapshot_date >= expected_date:
        return 0
    return count_business_days(snapshot_date + timedelta(days=1), expected_date)
