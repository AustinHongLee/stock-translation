from __future__ import annotations

import unittest
from datetime import date

from app.analyze.data_gap import (
    DATA_NODE_DAILY_PRICE,
    DEPTH_DEEP,
    DEPTH_EMPTY,
    DEPTH_LATEST_ONLY,
    DEPTH_SHALLOW,
    DEPTH_USABLE,
    STATUS_CURRENT,
    STATUS_FORCE_REFRESH_REQUIRED,
    STATUS_GAP,
    STATUS_PATCHED,
    STATUS_SOURCE_PENDING,
    STATUS_SUSPECT,
    assess_daily_depth,
    count_business_days,
    market_node_freshness,
    next_business_day,
    plan_data_gap,
    previous_business_day,
    resolve_post_patch_status,
    same_month_tail_date,
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

    def test_latest_only_daily_rows_force_history_backfill(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-22", "row_count": 2},
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )

        self.assertEqual(plan.status, STATUS_FORCE_REFRESH_REQUIRED)
        self.assertEqual(plan.fetch_start_date, date(2025, 6, 22))
        self.assertEqual(plan.fetch_end_date, date(2026, 6, 22))
        self.assertTrue(plan.force_refresh_required)

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
        self.assertEqual(plan.fetch_start_date, date(2026, 6, 22))
        self.assertEqual(plan.fetch_end_date, date(2026, 6, 22))
        self.assertEqual(plan.gap_business_days, 1)
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
            resolve_post_patch_status(plan, latest_date=date(2026, 6, 18), rows_written=1).status,
            STATUS_SOURCE_PENDING,
        )
        self.assertEqual(
            resolve_post_patch_status(plan, latest_date=date(2026, 6, 17), rows_written=1).status,
            STATUS_SUSPECT,
        )

    def test_post_patch_status_keeps_recent_tail_hole_suspect(self) -> None:
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={
                "latest_date": "2026-07-07",
                "row_count": 250,
                "horizon_row_count": 250,
                "tail_hole_count": 10,
                "tail_gap_start_date": "2026-06-23",
                "tail_gap_end_date": "2026-07-06",
            },
            target_date=date(2026, 7, 7),
            lookback_days=365,
        )

        status = resolve_post_patch_status(
            plan,
            latest_date=date(2026, 7, 7),
            rows_written=0,
            coverage={"tail_hole_count": 10},
        )

        self.assertEqual(status.status, STATUS_SUSPECT)
        self.assertIn("missing trading day", status.reason)

    def test_business_day_count_skips_weekends_and_twse_holidays(self) -> None:
        self.assertEqual(count_business_days(date(2026, 6, 19), date(2026, 6, 22)), 1)
        self.assertEqual(previous_business_day(date(2026, 6, 21)), date(2026, 6, 18))
        self.assertEqual(next_business_day(date(2026, 6, 19)), date(2026, 6, 22))

    def test_market_node_freshness_current_gap_missing_and_grace(self) -> None:
        self.assertEqual(
            market_node_freshness(date(2026, 6, 22), date(2026, 6, 22))["status"],
            STATUS_CURRENT,
        )
        self.assertEqual(
            market_node_freshness(date(2026, 6, 18), date(2026, 6, 22), grace_business_days=0),
            {"status": STATUS_GAP, "gap_business_days": 1, "latest_date": "2026-06-18"},
        )
        self.assertEqual(
            market_node_freshness(date(2026, 6, 18), date(2026, 6, 22), grace_business_days=1)["status"],
            STATUS_CURRENT,
        )
        self.assertEqual(
            market_node_freshness(None, date(2026, 6, 22)),
            {"status": "missing", "gap_business_days": 0, "latest_date": None},
        )
        self.assertEqual(
            market_node_freshness(date(2026, 6, 18), None)["status"],
            STATUS_SOURCE_PENDING,
        )

    def test_depth_levels_follow_expected_trading_days(self) -> None:
        target = date(2026, 6, 22)
        expected = count_business_days(date(2025, 6, 22), target)

        deep = assess_daily_depth(
            coverage={
                "row_count": int(expected * 0.95),
                "earliest_date": "2025-07-01",
                "latest_date": "2026-06-22",
            },
            target_date=target,
        )
        self.assertEqual(deep.level, DEPTH_DEEP)
        self.assertFalse(deep.needs_backfill)

        usable = assess_daily_depth(
            coverage={
                "row_count": int(expected * 0.6),
                "earliest_date": "2025-11-01",
                "latest_date": "2026-06-22",
            },
            target_date=target,
        )
        self.assertEqual(usable.level, DEPTH_USABLE)
        self.assertFalse(usable.needs_backfill)

        shallow = assess_daily_depth(
            coverage={
                "row_count": int(expected * 0.3),
                "earliest_date": "2026-02-01",
                "latest_date": "2026-06-22",
            },
            target_date=target,
        )
        self.assertEqual(shallow.level, DEPTH_SHALLOW)
        self.assertTrue(shallow.needs_backfill)

        latest_only = assess_daily_depth(
            coverage={
                "row_count": 2,
                "earliest_date": "2026-06-18",
                "latest_date": "2026-06-22",
            },
            target_date=target,
        )
        self.assertEqual(latest_only.level, DEPTH_LATEST_ONLY)
        self.assertTrue(latest_only.needs_backfill)

        empty = assess_daily_depth(coverage={"row_count": 0}, target_date=target)
        self.assertEqual(empty.level, DEPTH_EMPTY)
        self.assertTrue(empty.needs_backfill)

    def test_invariant_fresh_but_shallow_is_never_current(self) -> None:
        # 防回歸主約束：latest 頂到 target 但近一年筆數遠低於期望時，
        # 永遠不得判 current——不論筆數是 1 還是 40。
        # 用迴圈掃參數空間，未來任何「常數門檻」式修法（5 也好、50 也好）都會被抓到。
        target = date(2026, 6, 22)
        for rows in range(1, 41):
            plan = plan_data_gap(
                stock_id="2330",
                node=DATA_NODE_DAILY_PRICE,
                coverage={
                    "latest_date": "2026-06-22",
                    "row_count": rows,
                    "earliest_date": "2026-04-01",
                },
                target_date=target,
                lookback_days=365,
            )
            self.assertNotEqual(plan.status, STATUS_CURRENT, msg=f"rows={rows}")
            self.assertTrue(plan.force_refresh_required, msg=f"rows={rows}")
            self.assertEqual(plan.fetch_start_date, date(2025, 6, 22), msg=f"rows={rows}")

    def test_accumulated_topup_rows_still_require_backfill(self) -> None:
        # 事故殘餘地雷：受災股被每日 top-up 累到 10 筆（> 舊門檻 5），
        # 舊常數門檻會誤判 current → 歷史永遠補不回。深度軸必須攔下。
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={
                "latest_date": "2026-06-22",
                "row_count": 10,
                "earliest_date": "2026-06-05",
            },
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )
        self.assertEqual(plan.status, STATUS_FORCE_REFRESH_REQUIRED)
        self.assertIsNotNone(plan.depth)
        self.assertTrue(plan.depth.needs_backfill)

    def test_depth_uses_horizon_rows_not_total_rows(self) -> None:
        # 老資料很多但近一年只有最新一天，仍然要補歷史；不能用總筆數自我安慰成 deep。
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={
                "latest_date": "2026-06-22",
                "earliest_date": "2021-01-01",
                "row_count": 260,
                "horizon_row_count": 1,
            },
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )

        self.assertEqual(plan.status, STATUS_FORCE_REFRESH_REQUIRED)
        self.assertEqual(plan.depth.level, DEPTH_SHALLOW)
        self.assertEqual(plan.depth.row_count, 1)

    def test_recent_tail_hole_is_not_current_even_when_latest_reaches_target(self) -> None:
        # 例如圖上從 6/22 直接跳 7/7：latest 看起來到位，但 K 線尾端缺交易日。
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={
                "latest_date": "2026-07-07",
                "earliest_date": "2025-07-07",
                "row_count": 250,
                "horizon_row_count": 250,
                "tail_hole_count": 10,
                "tail_gap_start_date": "2026-06-23",
                "tail_gap_end_date": "2026-07-06",
            },
            target_date=date(2026, 7, 7),
            lookback_days=365,
        )

        self.assertEqual(plan.status, STATUS_GAP)
        self.assertFalse(plan.force_refresh_required)
        self.assertTrue(plan.can_patch)
        self.assertEqual(plan.fetch_start_date, date(2026, 6, 23))
        self.assertEqual(plan.fetch_end_date, date(2026, 7, 7))
        self.assertIn("missing recent trading day", plan.reason)

    def test_new_listing_with_full_history_since_listing_is_current(self) -> None:
        # 上市 2 個交易日、2 筆都在 → 期望深度以上市日推導 → current。
        # 舊門檻會每次強制重抓 13 個月（幾乎全空），形成 ping-pong。
        plan = plan_data_gap(
            stock_id="9999",
            node=DATA_NODE_DAILY_PRICE,
            coverage={
                "latest_date": "2026-06-22",
                "row_count": 2,
                "earliest_date": "2026-06-18",
            },
            target_date=date(2026, 6, 22),
            lookback_days=365,
            listed_date=date(2026, 6, 18),
        )
        self.assertEqual(plan.status, STATUS_CURRENT)
        self.assertEqual(plan.depth.level, DEPTH_DEEP)

    def test_new_listing_initial_backfill_starts_at_listed_date(self) -> None:
        plan = plan_data_gap(
            stock_id="9999",
            node=DATA_NODE_DAILY_PRICE,
            coverage=None,
            target_date=date(2026, 6, 22),
            lookback_days=365,
            listed_date=date(2026, 6, 18),
        )
        self.assertEqual(plan.status, STATUS_GAP)
        self.assertEqual(plan.fetch_start_date, date(2026, 6, 18))

    def test_depth_without_row_count_stays_lenient(self) -> None:
        # 極簡 coverage（只有 latest_date）：深度未知不強制回補，維持舊語意。
        plan = plan_data_gap(
            stock_id="2330",
            node=DATA_NODE_DAILY_PRICE,
            coverage={"latest_date": "2026-06-22"},
            target_date=date(2026, 6, 22),
            lookback_days=365,
        )
        self.assertEqual(plan.status, STATUS_CURRENT)

    def test_same_month_tail_date_never_crosses_into_extra_month(self) -> None:
        self.assertEqual(same_month_tail_date(date(2026, 6, 29), date(2026, 6, 30)), date(2026, 6, 30))
        self.assertEqual(same_month_tail_date(date(2026, 6, 29), date(2026, 7, 3)), date(2026, 6, 30))
        self.assertEqual(same_month_tail_date(date(2026, 6, 29), date(2026, 6, 28)), date(2026, 6, 29))


if __name__ == "__main__":
    unittest.main()
