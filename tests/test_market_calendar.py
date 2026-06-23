from __future__ import annotations

import unittest
from datetime import date

from app.analyze.market_calendar import (
    previous_completed_business_day,
    resolve_market_target_date,
)


class MarketCalendarTests(unittest.TestCase):
    def test_previous_completed_business_day_skips_weekend(self) -> None:
        self.assertEqual(previous_completed_business_day(date(2026, 6, 22)), date(2026, 6, 19))
        self.assertEqual(previous_completed_business_day(date(2026, 6, 23)), date(2026, 6, 22))

    def test_recent_snapshot_remains_authoritative(self) -> None:
        target = resolve_market_target_date(
            reference_date=date(2026, 6, 22),
            market_latest_date=date(2026, 6, 22),
            as_of=date(2026, 6, 23),
        )

        self.assertEqual(target.target_date, date(2026, 6, 22))
        self.assertEqual(target.source, "stock_snapshot")
        self.assertFalse(target.snapshot_stale)

    def test_stale_snapshot_falls_back_to_expected_close_date(self) -> None:
        target = resolve_market_target_date(
            reference_date=date(2026, 6, 18),
            market_latest_date=date(2026, 6, 18),
            as_of=date(2026, 6, 23),
        )

        self.assertEqual(target.target_date, date(2026, 6, 22))
        self.assertEqual(target.source, "calendar_fallback")
        self.assertEqual(target.snapshot_lag_business_days, 2)
        self.assertTrue(target.snapshot_stale)

    def test_recently_checked_snapshot_can_stay_on_old_price_date(self) -> None:
        target = resolve_market_target_date(
            reference_date=date(2026, 6, 18),
            market_latest_date=date(2026, 6, 18),
            snapshot_checked_date=date(2026, 6, 23),
            as_of=date(2026, 6, 23),
        )

        self.assertEqual(target.target_date, date(2026, 6, 18))
        self.assertEqual(target.snapshot_lag_business_days, 2)
        self.assertEqual(target.snapshot_checked_lag_business_days, 0)
        self.assertFalse(target.snapshot_stale)


if __name__ == "__main__":
    unittest.main()
