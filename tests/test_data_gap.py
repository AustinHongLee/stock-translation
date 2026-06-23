from __future__ import annotations

import unittest
from datetime import date

from app.analyze.data_gap import (
    DATA_NODE_DAILY_PRICE,
    STATUS_CURRENT,
    STATUS_FORCE_REFRESH_REQUIRED,
    STATUS_GAP,
    STATUS_PATCHED,
    STATUS_SOURCE_PENDING,
    STATUS_SUSPECT,
    count_business_days,
    plan_data_gap,
    resolve_post_patch_status,
)


class DataGapTests(unittest.TestCase):
    def test_current_plan_skips_fetch(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-22"},
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )

        self.assertEqual(plan.status, STATUS_CURRENT)
        self.assertIsNone(plan.fetch_start_date)
        self.assertFalse(plan.can_patch)

    def test_small_gap_patches_only_missing_business_days(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-18"},
            target_date=date(2026, 6, 22),
            lookback_days=365,
            max_patch_business_days=10,
        )

        self.assertEqual(plan.status, STATUS_GAP)
        self.assertEqual(plan.fetch_start_date, date(2026, 6, 19))
        self.assertEqual(plan.fetch_end_date, date(2026, 6, 22))
        self.assertEqual(plan.gap_business_days, 2)
        self.assertTrue(plan.can_patch)

    def test_large_gap_trips_refresh_gate(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-01-02"},
            target_date=date(2026, 6, 22),
            lookback_days=365,
            max_patch_business_days=10,
        )

        self.assertEqual(plan.status, STATUS_FORCE_REFRESH_REQUIRED)
        self.assertFalse(plan.can_patch)
        self.assertTrue(plan.force_refresh_required)

    def test_missing_target_is_source_pending(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-18"},
            target_date=None,
            lookback_days=365,
        )

        self.assertEqual(plan.status, STATUS_SOURCE_PENDING)
        self.assertIsNone(plan.fetch_start_date)

    def test_post_patch_status_distinguishes_pending_and_suspect(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-18"},
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )

        self.assertEqual(
            resolve_post_patch_status(plan, latest_date=date(2026, 6, 22), rows_written=2).status,
            STATUS_PATCHED,
        )
        self.assertEqual(
            resolve_post_patch_status(plan, latest_date=date(2026, 6, 18), rows_written=0).status,
            STATUS_SOURCE_PENDING,
        )
        self.assertEqual(
            resolve_post_patch_status(plan, latest_date=date(2026, 6, 20), rows_written=1).status,
            STATUS_SUSPECT,
        )

    def test_business_day_count_skips_weekends(self) -> None:
        self.assertEqual(count_business_days(date(2026, 6, 19), date(2026, 6, 22)), 2)


if __name__ == "__main__":
    unittest.main()
