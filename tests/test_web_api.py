from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    IntradayQuote,
    InstitutionalTrade,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.analyze.data_gap import DATA_NODE_DAILY_PRICE, DATA_NODE_INSTITUTIONAL
from app.analyze.twse_calendar import is_twse_trading_day
from app.analyze.suitability import ValuationSuitability
from app.news.classifier import contains_forbidden
from app.store.sqlite_store import SQLiteStore
from app.glossary.service import glossary_payload
from app.portfolio.models import PortfolioTransaction
from app.web.api import (
    LOCAL_DATA_CACHE_KEY,
    build_compare_payload,
    build_cached_local_data_payload,
    build_chart_annotations_payload,
    build_indicator_catalog_payload,
    build_indicator_prefs_payload,
    build_local_data_payload,
    build_market_radar_payload,
    build_portfolio_payload,
    build_search_payload,
    build_sync_freshness_payload,
    build_stock_payload,
    build_watchlist_payload,
    create_chart_annotation_payload,
    save_indicator_prefs_payload,
    stock_brief_to_json,
    update_chart_annotation_payload,
)


class WebApiPayloadTests(unittest.TestCase):
    def test_sync_freshness_uses_recent_close_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-22"},
                            {"stock_id": "2303", "price_date": "2026-06-21"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 22) - timedelta(days=offset),
                            open=100,
                            high=105,
                            low=99,
                            close=104,
                            volume=10,
                        )
                        # 歷史深度足夠，避免觸發「已最新但歷史不足」的回補判定。
                        for offset in range(400)
                    ]
                )

                current = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 6, 22),
                )
                stale = build_sync_freshness_payload(
                    store,
                    "2303",
                    screener_path=screener_path,
                    today=date(2026, 6, 22),
                )
                self.assertIsNone(store.get_data_coverage("2330", DATA_NODE_DAILY_PRICE))
                self.assertIsNone(store.get_data_coverage("2330", DATA_NODE_INSTITUTIONAL))

        self.assertTrue(current["is_current"])
        self.assertTrue(current["can_skip_sync"])
        self.assertEqual(current["reference_latest_date"], "2026-06-22")
        self.assertEqual(current["daily_price"]["gap"]["status"], "current")
        self.assertEqual(current["institutional"]["gap"]["status"], "missing")
        self.assertFalse(stale["is_current"])
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["daily_price"]["gap"]["target_date"], "2026-06-21")

    def test_sync_freshness_marks_stale_snapshot_and_uses_fallback_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-17"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 17), 100, 105, 99, 104, 10),
                    ]
                )

                payload = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 6, 23),
                )

        self.assertEqual(payload["status"], "stale_snapshot")
        self.assertFalse(payload["can_skip_sync"])
        self.assertTrue(payload["snapshot_stale"])
        self.assertEqual(payload["snapshot_lag_business_days"], 2)
        self.assertEqual(payload["reference_latest_date"], "2026-06-17")
        self.assertEqual(payload["target_latest_date"], "2026-06-22")
        self.assertEqual(payload["daily_price"]["gap"]["target_date"], "2026-06-22")

    def test_sync_freshness_does_not_trust_recently_checked_old_price_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-06-23T08:30:00+00:00",
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-17"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 17), 100, 105, 99, 104, 10),
                    ]
                )

                payload = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 6, 23),
                )

        self.assertEqual(payload["status"], "stale_snapshot")
        self.assertFalse(payload["can_skip_sync"])
        self.assertTrue(payload["snapshot_stale"])
        self.assertEqual(payload["target_latest_date"], "2026-06-22")
        self.assertEqual(payload["target_source"], "calendar_fallback")

    def test_sync_freshness_targets_yesterday_when_snapshot_stops_one_day_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-06-23T08:30:00+00:00",
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-22"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 22), 100, 105, 99, 104, 10),
                    ]
                )

                payload = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 6, 24),
                )

        self.assertEqual(payload["status"], "stale_snapshot")
        self.assertFalse(payload["can_skip_sync"])
        self.assertEqual(payload["local_latest_date"], "2026-06-22")
        self.assertEqual(payload["reference_latest_date"], "2026-06-22")
        self.assertEqual(payload["expected_latest_close_date"], "2026-06-23")
        self.assertEqual(payload["target_latest_date"], "2026-06-23")
        self.assertEqual(payload["daily_price"]["gap"]["status"], "gap")
        self.assertEqual(payload["daily_price"]["gap"]["target_date"], "2026-06-23")

    def test_sync_freshness_flags_fresh_but_shallow_history(self) -> None:
        # 防回歸：latest 頂到 target 但近一年只有幾筆 → 不可 can_skip_sync，
        # 要提示補歷史（shallow_history），而不是說「已是最新」。
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {"items": [{"stock_id": "2330", "price_date": "2026-06-22"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 22), 100, 105, 99, 104, 10),
                        DailyPrice("2330", date(2026, 6, 17), 100, 105, 99, 104, 10),
                        DailyPrice("2330", date(2026, 6, 16), 100, 105, 99, 104, 10),
                    ]
                )

                payload = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 6, 22),
                )

        self.assertEqual(payload["status"], "shallow_history")
        self.assertFalse(payload["can_skip_sync"])
        self.assertFalse(payload["is_current"])
        self.assertEqual(payload["daily_price"]["gap"]["status"], "force_refresh_required")  # type: ignore[index]
        self.assertTrue(payload["daily_price"]["gap"]["depth"]["needs_backfill"])  # type: ignore[index]

    def test_sync_freshness_flags_fresh_but_recent_tail_has_hole(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {"items": [{"stock_id": "2330", "price_date": "2026-07-08"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rows: list[DailyPrice] = []
            current = date(2025, 7, 7)
            while current <= date(2026, 7, 8):
                if is_twse_trading_day(current) and not (date(2026, 6, 23) <= current <= date(2026, 7, 6)):
                    rows.append(DailyPrice("2330", current, 100, 105, 99, 104, 10))
                current += timedelta(days=1)
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(rows)

                payload = build_sync_freshness_payload(
                    store,
                    "2330",
                    screener_path=screener_path,
                    today=date(2026, 7, 8),
                )

        self.assertEqual(payload["status"], "data_hole")
        self.assertFalse(payload["can_skip_sync"])
        self.assertFalse(payload["is_current"])
        self.assertEqual(payload["daily_price"]["gap"]["status"], "gap")  # type: ignore[index]
        self.assertEqual(payload["daily_price"]["coverage"]["tail_hole_count"], 10)  # type: ignore[index]
        self.assertIn("K 線尾端中間缺 10 個交易日", payload["message"])

    def test_local_data_payload_exposes_report_date_and_target_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-17"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 17), 100, 105, 99, 104, 10),
                    ]
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 6, 23),
                    screener_path=screener_path,
                )

        self.assertEqual(payload["generated_at"], "2026-06-23")
        self.assertEqual(payload["data_target_date"], "2026-06-22")
        self.assertTrue(payload["data_target"]["snapshot_stale"])  # type: ignore[index]
        self.assertEqual(payload["items"][0]["data_target_date"], "2026-06-22")  # type: ignore[index]

    def test_local_data_refreshes_stale_coverage_before_gap_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-01T08:00:00+08:00",
                        "items": [{"stock_id": "1442", "price_date": "2026-06-30"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("1442", date(2026, 6, 29) - timedelta(days=offset), 26.7, 27.0, 26.5, 26.85, 10)
                        # 歷史深度足夠，此測試只驗證 coverage 過期後會先刷新再貼標籤。
                        for offset in range(400)
                    ]
                )
                store.refresh_data_coverage(
                    "1442",
                    DATA_NODE_DAILY_PRICE,
                    target_date=date(2026, 6, 30),
                )
                store.upsert_daily_prices(
                    [
                        DailyPrice("1442", date(2026, 6, 30), 26.8, 27.1, 26.7, 26.9, 10),
                    ]
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 7, 1),
                    screener_path=screener_path,
                )
                refreshed = store.get_data_coverage("1442", DATA_NODE_DAILY_PRICE)

        item = payload["items"][0]  # type: ignore[index]
        self.assertEqual(item["last_date"], "2026-06-30")  # type: ignore[index]
        self.assertEqual(item["price_gap"]["status"], "current")  # type: ignore[index]
        self.assertEqual(item["price_gap"]["local_latest_date"], "2026-06-30")  # type: ignore[index]
        self.assertEqual(item["history_depth"]["level"], "deep")  # type: ignore[index]
        self.assertEqual(refreshed["latest_date"], "2026-06-30")  # type: ignore[index]

    def test_local_data_depth_ignores_cached_total_rows_without_horizon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-06-23T08:00:00+08:00",
                        "items": [{"stock_id": "2330", "price_date": "2026-06-22"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                old_start = date(2024, 1, 1)
                rows = [
                    DailyPrice("2330", old_start + timedelta(days=offset), 100, 101, 99, 100, 10)
                    for offset in range(260)
                ]
                rows.append(DailyPrice("2330", date(2026, 6, 22), 101, 102, 100, 101, 12))
                store.upsert_daily_prices(rows)
                store.refresh_data_coverage(
                    "2330",
                    DATA_NODE_DAILY_PRICE,
                    target_date=date(2026, 6, 22),
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 6, 23),
                    screener_path=screener_path,
                )

        item = payload["items"][0]  # type: ignore[index]
        self.assertEqual(item["last_date"], "2026-06-22")  # type: ignore[index]
        self.assertEqual(item["history_depth"]["row_count"], 1)  # type: ignore[index]
        self.assertEqual(item["history_depth"]["level"], "shallow")  # type: ignore[index]
        self.assertEqual(item["price_gap"]["status"], "force_refresh_required")  # type: ignore[index]

    def test_local_data_profileless_market_product_short_history_requires_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-03T18:00:00+08:00",
                        "items": [{"stock_id": "00400A", "price_date": "2026-07-03"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("00400A", day, 10, 11, 9, 10, 10, source="TWSE_STOCK_DAY")
                        for day in (
                            date(2026, 6, 29),
                            date(2026, 6, 30),
                            date(2026, 7, 1),
                            date(2026, 7, 2),
                            date(2026, 7, 3),
                        )
                    ]
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 7, 6),
                    screener_path=screener_path,
                )

        item = payload["items"][0]  # type: ignore[index]
        self.assertEqual(item["stock_id"], "00400A")  # type: ignore[index]
        self.assertEqual(item["price_gap"]["status"], "force_refresh_required")  # type: ignore[index]
        self.assertEqual(item["history_depth"]["level"], "latest_only")  # type: ignore[index]
        self.assertEqual(item["history_depth"]["horizon_start"], "2025-07-03")  # type: ignore[index]
        self.assertEqual(item["price_source"]["level"], "historical")  # type: ignore[index]
        self.assertEqual(item["data_health"]["level"], "shallow_history")  # type: ignore[index]
        self.assertTrue(item["data_health"]["needs_backfill"])  # type: ignore[index]
        self.assertEqual(payload["health_summary"]["shallow_history_count"], 1)  # type: ignore[index]

    def test_profileless_market_product_short_window_requires_history_backfill(self) -> None:
        class July6Date(date):
            @classmethod
            def today(cls) -> "July6Date":
                return cls(2026, 7, 6)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {"items": [{"stock_id": "00405A", "price_date": "2026-07-03"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("00405A", day, 10, 11, 9, 10, 10)
                        for day in (
                            date(2026, 6, 29),
                            date(2026, 6, 30),
                            date(2026, 7, 2),
                            date(2026, 7, 3),
                        )
                    ]
                )

                with patch("app.web.api.date", July6Date):
                    stock_payload = build_stock_payload(store, "00405A", days=365)
                freshness = build_sync_freshness_payload(
                    store,
                    "00405A",
                    screener_path=screener_path,
                    today=date(2026, 7, 6),
                )

        self.assertEqual(stock_payload["price_window"]["expected_end"], "2026-07-03")  # type: ignore[index]
        self.assertEqual(stock_payload["price_window"]["actual_end"], "2026-07-03")  # type: ignore[index]
        self.assertEqual(stock_payload["price_window"]["stale_days"], 0)  # type: ignore[index]
        self.assertFalse(stock_payload["price_window"]["is_stale"])  # type: ignore[index]
        self.assertTrue(stock_payload["price_window"]["is_short_history"])  # type: ignore[index]
        self.assertFalse(freshness["can_skip_sync"])
        self.assertEqual(freshness["status"], "shallow_history")
        self.assertEqual(freshness["daily_price"]["gap"]["status"], "force_refresh_required")  # type: ignore[index]

    def test_profileless_etf_stock_page_uses_etf_identity(self) -> None:
        class July6Date(date):
            @classmethod
            def today(cls) -> "July6Date":
                return cls(2026, 7, 6)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            screener_path = Path(tmpdir) / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {"items": [{"stock_id": "00939", "price_date": "2026-07-03"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("00939", day, 21, 22, 20, 21.28, 1000)
                        for day in (
                            date(2026, 6, 29),
                            date(2026, 6, 30),
                            date(2026, 7, 2),
                            date(2026, 7, 3),
                        )
                    ]
                )

                with patch("app.web.api.date", July6Date):
                    payload = build_stock_payload(store, "00939", days=365)
                freshness = build_sync_freshness_payload(
                    store,
                    "00939",
                    screener_path=screener_path,
                    today=date(2026, 7, 6),
                )

        profile = payload["profile"]  # type: ignore[index]
        suitability = payload["valuation"]["suitability"]  # type: ignore[index]
        brief_text = json.dumps(payload["brief"], ensure_ascii=False)

        self.assertEqual(profile["stock_id"], "00939")  # type: ignore[index]
        self.assertEqual(profile["short_name"], "ETF/市場商品")  # type: ignore[index]
        self.assertIn("ETF/市場商品", profile["name"])  # type: ignore[index]
        self.assertEqual(suitability["company_type"], "etf")  # type: ignore[index]
        self.assertEqual(suitability["state"], "not_applicable")  # type: ignore[index]
        self.assertIn("etf", suitability["reasons"])  # type: ignore[index]
        self.assertIn("ETF", brief_text)
        self.assertIn("折溢價", brief_text)
        self.assertNotIn("一般股", brief_text)
        self.assertNotIn("這家公司 的產業資料待補", brief_text)
        self.assertEqual(contains_forbidden(brief_text), [])
        self.assertFalse(freshness["can_skip_sync"])
        self.assertEqual(freshness["status"], "shallow_history")

    def test_local_data_marks_latest_all_only_source_as_needing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {"items": [{"stock_id": "00939", "price_date": "2026-07-03"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            "00939",
                            day,
                            21,
                            22,
                            20,
                            21.28,
                            1000,
                            source="TWSE_STOCK_DAY_ALL",
                        )
                        for day in (
                            date(2026, 6, 29),
                            date(2026, 6, 30),
                            date(2026, 7, 2),
                            date(2026, 7, 3),
                        )
                    ]
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 7, 6),
                    screener_path=screener_path,
                )

        item = payload["items"][0]  # type: ignore[index]
        self.assertEqual(item["price_source"]["level"], "latest_all_only")  # type: ignore[index]
        self.assertEqual(item["data_health"]["level"], "latest_only")  # type: ignore[index]
        self.assertTrue(item["data_health"]["needs_backfill"])  # type: ignore[index]
        self.assertEqual(payload["health_summary"]["latest_only_count"], 1)  # type: ignore[index]
        self.assertEqual(payload["health_summary"]["latest_all_only_count"], 1)  # type: ignore[index]

    def test_local_data_uses_market_level_institutional_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "stock.sqlite3"
            screener_path = root / "value_screener.json"
            screener_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2330", "price_date": "2026-06-22"},
                            {"stock_id": "2303", "price_date": "2026-06-22"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 22), 100, 105, 99, 104, 10),
                        DailyPrice("2303", date(2026, 6, 22), 40, 42, 39, 41, 10),
                    ]
                )
                store.upsert_institutional_trades(
                    [
                        InstitutionalTrade("2330", date(2026, 6, 17), 100, 0, 0, 100),
                        InstitutionalTrade("9999", date(2026, 6, 22), 100, 0, 0, 100),
                    ]
                )

                payload = build_local_data_payload(
                    store,
                    today=date(2026, 6, 23),
                    screener_path=screener_path,
                )

        self.assertEqual(payload["market_institutional"]["status"], "current")  # type: ignore[index]
        for item in payload["items"]:  # type: ignore[union-attr]
            self.assertEqual(item["institutional_gap"], payload["market_institutional"])
        item_by_id = {item["stock_id"]: item for item in payload["items"]}  # type: ignore[union-attr]
        self.assertEqual(item_by_id["2330"]["institutional_last_date"], "2026-06-17")
        self.assertIsNone(item_by_id["2303"]["institutional_last_date"])

    def test_build_stock_payload_contains_profile_prices_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles(
                    [
                        StockProfile(
                            stock_id="2330",
                            name="台灣積體電路製造股份有限公司",
                            short_name="台積電",
                        )
                    ]
                )
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 10),
                            open=100,
                            high=105,
                            low=99,
                            close=102,
                            volume=10,
                        ),
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 11),
                            open=102,
                            high=108,
                            low=101,
                            close=107,
                            volume=12,
                        ),
                    ]
                )
                store.upsert_dividend_records(
                    [
                        DividendRecord(
                            stock_id="2330",
                            year=115,
                            period="第1季",
                            status="董事會決議",
                            board_date=date(2026, 5, 12),
                            shareholder_meeting_date=None,
                            cash_dividend=7.0,
                            stock_dividend=0.0,
                        )
                    ]
                )
                store.upsert_market_valuations(
                    [
                        MarketValuation(
                            stock_id="2330",
                            date=date(2026, 6, 11),
                            pe_ratio=30.25,
                            dividend_yield=0.98,
                            pb_ratio=9.9,
                        )
                    ]
                )
                store.upsert_monthly_revenues(
                    [
                        MonthlyRevenue(
                            stock_id="2330",
                            year_month="2026-05",
                            company_name="台積電",
                            industry="半導體業",
                            current_month_revenue=416975163,
                            previous_month_revenue=410725118,
                            last_year_month_revenue=320515951,
                            mom_percent=1.52,
                            yoy_percent=30.09,
                            cumulative_revenue=1961803721,
                            cumulative_last_year_revenue=1509336555,
                            cumulative_yoy_percent=29.98,
                            source_updated_at=date(2026, 6, 11),
                        )
                    ]
                )
                store.upsert_financial_statements(
                    [
                        FinancialStatement(
                            stock_id="2330",
                            year=2026,
                            quarter=1,
                            company_name="台積電",
                            revenue=1134103440,
                            gross_profit=751295421,
                            operating_income=658966142,
                            non_operating_income_expense=28833545,
                            pre_tax_income=687799687,
                            net_income=572801304,
                            parent_net_income=572479752,
                            eps=22.08,
                            total_assets=8660949685,
                            total_liabilities=2728560764,
                            parent_equity=5890960252,
                            total_equity=5932388921,
                            book_value_per_share=227.17,
                            source_updated_at=date(2026, 6, 12),
                        )
                    ]
                )
                store.add_to_watchlist("2330")
                store.add_portfolio_transaction(
                    PortfolioTransaction(
                        stock_id="2330",
                        trade_date=date(2026, 6, 1),
                        side="buy",
                        shares=1000,
                        price=100,
                        fee=10,
                        note="測試買進",
                    )
                )

                payload = build_stock_payload(
                    store,
                    "2330",
                    days=3650,
                    quote_provider=FakeQuoteProvider(),
                )
                portfolio_payload = build_portfolio_payload(store)
                search_payload = build_search_payload(store, "台積")
                watchlist_payload = build_watchlist_payload(store)

        self.assertEqual(payload["profile"]["short_name"], "台積電")  # type: ignore[index]
        self.assertEqual(len(payload["prices"]), 2)  # type: ignore[arg-type]
        self.assertEqual(payload["summary"]["latest_close"], 107)  # type: ignore[index]
        self.assertEqual(payload["quote"]["display_price"], 108)  # type: ignore[index]
        self.assertEqual(payload["quote"]["display_change"], 1)  # type: ignore[index]
        self.assertEqual(payload["monthly_revenues"][0]["year_month"], "2026-05")  # type: ignore[index]
        self.assertEqual(payload["revenue_summary"]["tone"], "positive")  # type: ignore[index]
        self.assertEqual(payload["financial_statements"][0]["eps"], 22.08)  # type: ignore[index]
        self.assertEqual(payload["financial_summary"]["tone"], "positive")  # type: ignore[index]
        self.assertGreater(payload["financial_statements"][0]["roe_percent"], 9)  # type: ignore[index]
        self.assertEqual(payload["fundamental_trends"]["sample_quarters"], 1)  # type: ignore[index]
        self.assertEqual(payload["fundamental_trends"]["series"][0]["label"], "毛利率")  # type: ignore[index]
        self.assertIn("historical_frequency", payload)
        self.assertEqual(len(payload["report"]["sections"]), 6)  # type: ignore[index]
        self.assertEqual(len(payload["validation"]["items"]), 3)  # type: ignore[index]
        self.assertEqual(payload["dividends"][0]["cash_dividend"], 7.0)  # type: ignore[index]
        self.assertEqual(payload["valuation"]["market"]["pe_ratio"], 30.25)  # type: ignore[index]
        self.assertEqual(payload["valuation"]["estimates"][0]["scenario"], "high_yield")  # type: ignore[index]
        self.assertNotIn("便宜價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertNotIn("合理價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertNotIn("昂貴價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertEqual(len(payload["valuation"]["vital_signs"]["facts"]), 4)  # type: ignore[index]
        self.assertGreaterEqual(len(payload["valuation"]["relative"]["methods"]), 1)  # type: ignore[index]
        self.assertTrue(payload["is_watchlisted"])
        self.assertIn("features", payload)
        self.assertNotIn("forecast_lab", payload)
        self.assertIn("ma20", payload["features"]["series"])  # type: ignore[index]
        self.assertEqual(len(payload["features"]["dates"]), len(payload["prices"]))  # type: ignore[index,arg-type]
        self.assertIn("structure", payload)
        self.assertEqual(payload["structure"]["title"], "結構指紋")  # type: ignore[index]
        self.assertEqual(portfolio_payload["summary"]["positions_count"], 1)  # type: ignore[index]
        self.assertEqual(portfolio_payload["positions"][0]["shares"], 1000)  # type: ignore[index]
        self.assertEqual(portfolio_payload["positions"][0]["latest_close"], 107)  # type: ignore[index]
        self.assertEqual(portfolio_payload["transactions"][0]["note"], "測試買進")  # type: ignore[index]
        self.assertIn("移動平均成本法", portfolio_payload["limitations"][0])  # type: ignore[index]
        self.assertEqual(search_payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(watchlist_payload["items"][0]["profile"]["short_name"], "台積電")  # type: ignore[index]
        self.assertIn("board", watchlist_payload["items"][0])  # type: ignore[index]
        self.assertEqual(watchlist_payload["items"][0]["board"]["assessment"]["label"], "體質中性")  # type: ignore[index]

    def test_stock_payload_caches_structure_by_last_close_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            today = date.today()
            rows = [
                DailyPrice(
                    stock_id="2330",
                    date=today - timedelta(days=319 - i),
                    open=100 + i * 0.1,
                    high=101 + i * 0.1,
                    low=99 + i * 0.1,
                    close=100 + i * 0.1 + ((i % 5) - 2) * 0.05,
                    volume=1000 + i,
                )
                for i in range(320)
            ]
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(rows)

                payload = build_stock_payload(store, "2330", days=365)
                last_date = rows[-1].date.isoformat()
                cached = store.get_json_cache(f"structure::2330::{last_date}::250")

                with patch("app.web.api.build_structure_payload", side_effect=AssertionError("recomputed")):
                    cached_payload = build_stock_payload(store, "2330", days=365)

        self.assertIsNotNone(cached)
        self.assertEqual(payload["structure"]["as_of_date"], last_date)  # type: ignore[index]
        self.assertEqual(cached_payload["structure"]["as_of_date"], last_date)  # type: ignore[index]
        self.assertEqual(len(cached_payload["structure"]["dimensions"]), 6)  # type: ignore[index]

    def test_stock_payload_structure_degrades_for_short_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            today = date.today()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="7777",
                            date=today - timedelta(days=49 - i),
                            open=50 + i * 0.1,
                            high=51 + i * 0.1,
                            low=49 + i * 0.1,
                            close=50 + i * 0.1,
                            volume=100 + i,
                        )
                        for i in range(50)
                    ]
                )

                payload = build_stock_payload(store, "7777", days=365)

        self.assertFalse(payload["structure"]["available"])  # type: ignore[index]
        self.assertEqual(payload["structure"]["sufficiency"]["grade"], "insufficient")  # type: ignore[index]
        self.assertEqual(len(payload["structure"]["dimensions"]), 6)  # type: ignore[index]

    def test_local_data_payload_does_not_compute_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date.today(),
                            open=100,
                            high=101,
                            low=99,
                            close=100,
                            volume=1000,
                        )
                    ]
                )

                with patch("app.web.api.build_structure_payload", side_effect=AssertionError("local-data recomputed structure")):
                    payload = build_local_data_payload(store)

        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["stock_id"], "2330")  # type: ignore[index]

    def test_market_radar_payload_degrades_when_local_universe_is_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(_market_radar_prices(stock_count=5, days=80))

                payload = build_market_radar_payload(store)

        self.assertFalse(payload["available"])
        self.assertIn("資料不足", payload["reason"])  # type: ignore[operator]
        self.assertEqual(payload["metrics"], [])

    def test_market_radar_payload_builds_metrics_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(_market_radar_prices(stock_count=35, days=90))

                payload = build_market_radar_payload(store, window=80, universe_size=30)
                cache_key = payload["cache_key"]  # type: ignore[index]
                cached = store.get_json_cache(str(cache_key))

                with patch("app.web.api.build_market_radar_metrics", side_effect=AssertionError("recomputed")):
                    cached_payload = build_market_radar_payload(store, window=80, universe_size=30)

        self.assertTrue(payload["available"])
        self.assertEqual(payload["title"], "市場心智雷達")
        self.assertEqual(payload["universe_size"], 30)
        self.assertEqual([item["key"] for item in payload["metrics"]], ["dispersion", "herding", "synchrony"])  # type: ignore[index]
        self.assertIsNotNone(cached)
        self.assertEqual(cached_payload["cache_key"], cache_key)

    def test_market_radar_payload_excludes_misaligned_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            rows = _market_radar_prices_from(
                id_start=1000,
                stock_count=35,
                start=date(2026, 4, 1),
                days=90,
                trade_boost=1,
            )
            rows.extend(
                _market_radar_prices_from(
                    id_start=9000,
                    stock_count=5,
                    start=date(2025, 9, 1),
                    days=90,
                    trade_boost=1000,
                )
            )
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(rows)

                payload = build_market_radar_payload(store, window=80, universe_size=40)

        self.assertTrue(payload["available"])
        self.assertEqual(payload["candidate_universe_size"], 40)
        self.assertEqual(payload["eligible_stock_count"], 40)
        self.assertEqual(payload["universe_size"], 35)
        self.assertEqual(payload["excluded_stock_count"], 5)
        self.assertGreaterEqual(payload["aligned_trading_days"], 60)

    def test_glossary_payload_is_available_for_ui_terms(self) -> None:
        payload = glossary_payload()

        self.assertIn("entries", payload)
        self.assertIn("收盤", payload["aliases"])

    def test_indicator_catalog_payload_is_registry_driven(self) -> None:
        payload = build_indicator_catalog_payload()
        keys = {item["key"] for item in payload["features"]}  # type: ignore[index]

        self.assertIn("ma20", keys)
        self.assertIn("ema200", keys)
        self.assertIn("newbie", payload["presets"])  # type: ignore[operator]

    def test_indicator_prefs_and_annotations_payloads_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles([StockProfile("2330", "台積電", "台積電")])
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 20), 100, 101, 99, 100, 1000),
                        DailyPrice("2330", date(2026, 6, 21), 101, 102, 100, 101, 1100),
                    ]
                )
                prefs = save_indicator_prefs_payload(
                    store,
                    {
                        "preset": "technical",
                        "enabled": ["ma20", "rsi_14"],
                        "chart_height": "tall",
                        "scale": "percent",
                        "ux_mode": "advanced",
                    },
                )
                annotation = create_chart_annotation_payload(
                    store,
                    "2330",
                    {
                        "kind": "note",
                        "anchor_date": "2026-06-21",
                        "anchor_price": 101,
                        "text": "測試筆記",
                    },
                )
                updated = update_chart_annotation_payload(
                    store,
                    "2330",
                    int(annotation["id"]),
                    {"text": "更新筆記"},
                )
                annotations = build_chart_annotations_payload(store, "2330")
                loaded_prefs = build_indicator_prefs_payload(store)
                stock_payload = build_stock_payload(store, "2330", days=10, quote_provider=FakeQuoteProvider())

        self.assertEqual(prefs["preset"], "technical")
        self.assertEqual(loaded_prefs["chart_height"], "tall")
        self.assertEqual(loaded_prefs["ux_mode"], "advanced")
        self.assertEqual(updated["text"], "更新筆記")
        self.assertEqual(annotations["items"][0]["text"], "更新筆記")  # type: ignore[index]
        self.assertEqual(stock_payload["indicator_prefs"]["scale"], "percent")  # type: ignore[index]
        self.assertEqual(stock_payload["indicator_prefs"]["ux_mode"], "advanced")  # type: ignore[index]
        self.assertEqual(stock_payload["annotations"][0]["text"], "更新筆記")  # type: ignore[index]

    def test_stock_payload_includes_ma_warmup_prices_without_expanding_visible_prices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            start = date(2026, 1, 1)
            with SQLiteStore(db_path) as store:
                store.upsert_profiles([StockProfile("2330", "台積電", "台積電")])
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            "2330",
                            start + timedelta(days=i),
                            100 + i,
                            101 + i,
                            99 + i,
                            100 + i,
                            1000,
                        )
                        for i in range(80)
                    ]
                )

                payload = build_stock_payload(store, "2330", days=10)

        self.assertEqual(len(payload["prices"]), 10)  # type: ignore[arg-type]
        self.assertEqual(len(payload["ma_prices"]), 80)  # type: ignore[arg-type]
        self.assertEqual(payload["prices"][0]["date"], "2026-03-12")  # type: ignore[index]
        self.assertEqual(payload["ma_prices"][0]["date"], "2026-01-01")  # type: ignore[index]
        self.assertEqual(len(payload["features"]["dates"]), 10)  # type: ignore[index,arg-type]
        self.assertIsNotNone(payload["features"]["series"]["ma60"][0])  # type: ignore[index]
        self.assertEqual(payload["features"]["dates"][0], payload["prices"][0]["date"])  # type: ignore[index]
        self.assertIn("chart_tour", payload)
        self.assertIn("relationships", payload)
        self.assertIn("items", payload["relationships"])  # type: ignore[operator]
        self.assertIn("beats", payload["chart_tour"])  # type: ignore[operator]

    def test_cached_local_data_payload_reuses_recent_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles([StockProfile("2330", "台積電", "台積電")])
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 1), 10, 11, 9, 10, 1000),
                        DailyPrice("2330", date(2026, 6, 2), 10, 12, 10, 11, 1000),
                    ]
                )

                first = build_cached_local_data_payload(store, max_age_seconds=60)
                store.upsert_daily_prices(
                    [DailyPrice("2303", date(2026, 6, 2), 20, 21, 19, 20, 1000)]
                )
                second = build_cached_local_data_payload(store, max_age_seconds=60)
                store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
                refreshed = build_cached_local_data_payload(store, max_age_seconds=60)

        self.assertFalse(first["cache"]["hit"])  # type: ignore[index]
        self.assertTrue(second["cache"]["hit"])  # type: ignore[index]
        self.assertEqual(second["count"], 1)
        self.assertEqual(refreshed["count"], 2)

    def test_build_compare_payload_reads_two_or_three_local_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles(
                    [
                        StockProfile("2330", "台灣積體電路製造股份有限公司", "台積電"),
                        StockProfile("2317", "鴻海精密工業股份有限公司", "鴻海"),
                        StockProfile("2454", "聯發科技股份有限公司", "聯發科"),
                        StockProfile("3008", "大立光電股份有限公司", "大立光"),
                    ]
                )
                for stock_id, start_close in [("2330", 100), ("2317", 200), ("2454", 300), ("3008", 400)]:
                    store.upsert_daily_prices(
                        [
                            DailyPrice(
                                stock_id=stock_id,
                                date=date(2026, 6, 1 + index),
                                open=start_close + index - 1,
                                high=start_close + index + 1,
                                low=start_close + index - 2,
                                close=start_close + index,
                                volume=1000 + index,
                            )
                            for index in range(20)
                        ]
                    )
                    store.upsert_institutional_trades(
                        [
                            InstitutionalTrade(
                                stock_id=stock_id,
                                date=date(2026, 6, 1 + index),
                                foreign_net=1000,
                                trust_net=0,
                                dealer_net=0,
                                total_net=1000,
                            )
                            for index in range(20)
                        ]
                    )

                payload = build_compare_payload(store, "2330,2317,2454,3008")

        self.assertEqual(payload["requested"], ["2330", "2317", "2454"])
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["items"][0]["profile"]["short_name"], "台積電")  # type: ignore[index]
        self.assertIn("assessment", payload["items"][0])  # type: ignore[index]
        self.assertEqual(payload["items"][0]["chips"]["sum_20_lots"], 20)  # type: ignore[index]

    def test_build_search_payload_uses_catalog_for_unsynced_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            catalog_path = tmp_path / "stock_catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2303", "market": "TWSE", "name": "聯電", "short_name": "聯電"},
                            {"stock_id": "2330", "market": "TWSE", "name": "台積電", "short_name": "台積電"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            db_path = tmp_path / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                payload = build_search_payload(store, "台積", catalog_path=catalog_path)

                store.upsert_profiles(
                    [
                        StockProfile(
                            stock_id="2330",
                            name="台灣積體電路製造股份有限公司",
                            short_name="台積電",
                        )
                    ]
                )
                synced_payload = build_search_payload(store, "台積", catalog_path=catalog_path)

        self.assertEqual(payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertFalse(payload["results"][0]["is_local"])  # type: ignore[index]
        self.assertEqual(synced_payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertTrue(synced_payload["results"][0]["is_local"])  # type: ignore[index]

    def test_stock_brief_adds_beginner_sentence_and_watch_items(self) -> None:
        suitability = ValuationSuitability(
            company_type="growth",
            company_type_label="成長股",
            state="low_confidence",
            reasons=["growth_stock", "low_yield"],
            recommended_primary="pe_band",
            recommended_secondary=["revenue_momentum"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="股利法參考性偏低，需搭配其他方法",
        )
        brief = stock_brief_to_json(
            StockProfile(
                stock_id="2330",
                name="台灣積體電路製造股份有限公司",
                short_name="台積電",
                industry_code="24",
            ),
            suitability,
        )
        text = json.dumps(brief, ensure_ascii=False)

        self.assertIn("beginner_sentence", brief)
        self.assertIn("watch_items", brief)
        self.assertIn("營收動能", text)
        self.assertIn("股利不是主軸", text)
        self.assertEqual(contains_forbidden(text), [])

    def test_stock_brief_etf_route_uses_etf_language(self) -> None:
        suitability = ValuationSuitability(
            company_type="etf",
            company_type_label="ETF",
            state="not_applicable",
            reasons=["etf"],
            recommended_primary="distribution_yield_band",
            recommended_secondary=["premium_discount"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="ETF 不適用個股股利法",
        )
        brief = stock_brief_to_json(None, suitability)
        text = json.dumps(brief, ensure_ascii=False)

        self.assertIn("ETF", text)
        self.assertIn("折溢價", text)
        self.assertEqual(contains_forbidden(text), [])


class FakeQuoteProvider:
    def fetch_quote(self, stock_id: str) -> IntradayQuote:
        return IntradayQuote(
            stock_id=stock_id,
            name="台積電",
            full_name="台灣積體電路製造股份有限公司",
            trade_datetime=None,
            current_price=108,
            previous_close=107,
            open_price=106,
            high_price=109,
            low_price=105,
            volume=100,
            best_bid_price=107.5,
            best_ask_price=108,
            bid_prices=(107.5,),
            ask_prices=(108,),
        )


def _market_radar_prices(*, stock_count: int, days: int) -> list[DailyPrice]:
    return _market_radar_prices_from(
        id_start=1000,
        stock_count=stock_count,
        start=date(2026, 1, 1),
        days=days,
    )


def _market_radar_prices_from(
    *,
    id_start: int,
    stock_count: int,
    start: date,
    days: int,
    trade_boost: int = 1,
) -> list[DailyPrice]:
    rows: list[DailyPrice] = []
    for stock_idx in range(stock_count):
        stock_id = f"{id_start + stock_idx}"
        base = 40 + stock_idx * 1.7
        for day_idx in range(days):
            close = base + day_idx * 0.05 + ((stock_idx + day_idx) % 7) * 0.03
            volume = (1000 + stock_idx * 10 + day_idx) * trade_boost
            rows.append(
                DailyPrice(
                    stock_id=stock_id,
                    date=start + timedelta(days=day_idx),
                    open=close - 0.2,
                    high=close + 0.4,
                    low=close - 0.5,
                    close=close,
                    volume=volume,
                    trade_value=int(volume * close),
                )
            )
    return rows


if __name__ == "__main__":
    unittest.main()
