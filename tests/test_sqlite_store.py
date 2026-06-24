from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    InstitutionalTrade,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.portfolio.models import PortfolioTransaction
from app.store.sqlite_store import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def test_profiles_and_prices_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles(
                    [
                        StockProfile(
                            stock_id="2330",
                            name="台灣積體電路製造股份有限公司",
                            short_name="台積電",
                            industry_code="24",
                            listed_date=date(1994, 9, 5),
                        )
                    ]
                )
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 1),
                            open=2355.0,
                            high=2415.0,
                            low=2350.0,
                            close=2355.0,
                            volume=60942792,
                        )
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

                profile = store.get_profile("2330")
                prices = store.get_daily_prices("2330")
                results = store.search_profiles("台積")
                dividends = store.get_dividend_records("2330")
                valuation = store.get_latest_market_valuation("2330")
                revenues = store.get_monthly_revenues("2330")
                financial = store.get_latest_financial_statement("2330")

            self.assertIsNotNone(profile)
            self.assertEqual(profile.short_name, "台積電")
            self.assertEqual(len(prices), 1)
            self.assertEqual(prices[0].close, 2355.0)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].stock_id, "2330")
            self.assertEqual(dividends[0].cash_dividend, 7.0)
            self.assertEqual(valuation.pe_ratio, 30.25)  # type: ignore[union-attr]
            self.assertEqual(revenues[0].year_month, "2026-05")
            self.assertEqual(revenues[0].yoy_percent, 30.09)
            self.assertEqual(financial.eps, 22.08)  # type: ignore[union-attr]
            self.assertEqual(financial.book_value_per_share, 227.17)  # type: ignore[union-attr]

    def test_watchlist_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                self.assertFalse(store.is_watchlisted("2330"))
                store.add_to_watchlist("2330")
                self.assertTrue(store.is_watchlisted("2330"))
                self.assertEqual(len(store.list_watchlist()), 1)
                store.remove_from_watchlist("2330")
                self.assertFalse(store.is_watchlisted("2330"))

    def test_bulk_progress_and_json_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.ensure_bulk_items("full_market", "stock", ["2330", "2303"])
                store.mark_bulk_item("full_market", "stock", "2330", "done")
                store.mark_bulk_item("full_market", "stock", "2303", "failed", error="no network")

                summary = store.get_bulk_progress_summary("full_market")
                failed = store.get_bulk_item_keys_by_status("full_market", "stock", "failed")
                statuses = store.get_bulk_item_statuses("full_market", "stock")

                store.set_json_cache("local_data_v1", {"count": 2, "items": [{"stock_id": "2330"}]})
                cached = store.get_json_cache("local_data_v1")
                store.delete_json_cache("local_data_v1")

            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["done"], 1)
            self.assertEqual(summary["failed_count"], 1)
            self.assertEqual(failed, ["2303"])
            self.assertEqual(statuses["2330"], "done")
            self.assertIsNotNone(cached)
            self.assertEqual(cached[0]["count"], 2)  # type: ignore[index]
            with SQLiteStore(db_path) as store:
                self.assertIsNone(store.get_json_cache("local_data_v1"))

    def test_indicator_prefs_and_chart_annotations_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                prefs = store.put_indicator_prefs(
                    {
                        "preset": "technical",
                        "enabled": ["ma20", "rsi_14"],
                        "chart_height": "tall",
                        "scale": "log",
                        "ux_mode": "advanced",
                        "experimental_ack": True,
                    }
                )
                loaded_prefs = store.get_indicator_prefs()
                self.assertEqual(prefs["ux_mode"], "advanced")
                self.assertEqual(loaded_prefs["ux_mode"], "advanced")  # type: ignore[index]
                annotation = store.add_chart_annotation(
                    "2330",
                    {
                        "kind": "note",
                        "anchor_date": "2026-06-22",
                        "anchor_price": 100,
                        "text": "觀察缺口",
                        "color": "#2C5475",
                    },
                )
                updated = store.update_chart_annotation(
                    "2330",
                    int(annotation["id"]),
                    {"text": "更新後筆記", "kind": "hline"},
                )
                annotations = store.get_chart_annotations("2330")
                store.delete_chart_annotation("2330", int(annotation["id"]))
                empty = store.get_chart_annotations("2330")

        self.assertEqual(prefs["preset"], "technical")
        self.assertEqual(loaded_prefs["enabled"], ["ma20", "rsi_14"])  # type: ignore[index]
        self.assertEqual(annotation["text"], "觀察缺口")
        self.assertEqual(updated["kind"], "hline")
        self.assertEqual(updated["text"], "更新後筆記")
        self.assertEqual(len(annotations), 1)
        self.assertEqual(empty, [])

    def test_data_coverage_refreshes_from_prices_and_institutional(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 18), 100, 101, 99, 100, 10),
                        DailyPrice("2330", date(2026, 6, 22), 101, 102, 100, 101, 12),
                    ]
                )
                store.upsert_institutional_trades(
                    [
                        InstitutionalTrade("2330", date(2026, 6, 18), 1, 2, 3, 6),
                        InstitutionalTrade("2330", date(2026, 6, 22), 2, 3, 4, 9),
                    ]
                )

                computed = store.compute_data_coverage(
                    "2330",
                    "daily_price",
                    target_date=date(2026, 6, 22),
                )
                self.assertIsNone(store.get_data_coverage("2330", "daily_price"))
                price_coverage = store.refresh_data_coverage(
                    "2330",
                    "daily_price",
                    target_date=date(2026, 6, 22),
                )
                inst_coverage = store.refresh_data_coverage(
                    "2330",
                    "institutional",
                    target_date=date(2026, 6, 23),
                )
                coverage_map = store.get_data_coverage_map("daily_price")

            self.assertEqual(computed["latest_date"], "2026-06-22")
            self.assertEqual(computed["status"], "current")
            self.assertEqual(price_coverage["latest_date"], "2026-06-22")
            self.assertEqual(price_coverage["row_count"], 2)
            self.assertEqual(price_coverage["hole_count"], 0)
            self.assertEqual(price_coverage["status"], "current")
            self.assertEqual(inst_coverage["latest_date"], "2026-06-22")
            self.assertEqual(inst_coverage["hole_count"], 0)
            self.assertEqual(inst_coverage["status"], "gap")
            self.assertEqual(coverage_map["2330"]["latest_date"], "2026-06-22")
            self.assertEqual(coverage_map["2330"]["row_count"], 2)

    def test_portfolio_transactions_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                transaction_id = store.add_portfolio_transaction(
                    PortfolioTransaction(
                        stock_id="2330",
                        trade_date=date(2026, 6, 1),
                        side="buy",
                        shares=1000,
                        price=900,
                        fee=100,
                        note="第一次建倉",
                    )
                )
                rows = store.get_portfolio_transactions()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].id, transaction_id)
                self.assertEqual(rows[0].stock_id, "2330")
                self.assertEqual(rows[0].note, "第一次建倉")

                store.update_portfolio_transaction(
                    PortfolioTransaction(
                        id=transaction_id,
                        stock_id="2330",
                        trade_date=date(2026, 6, 2),
                        side="buy",
                        shares=2000,
                        price=910,
                        fee=120,
                        note="調整後",
                    )
                )
                updated = store.get_portfolio_transactions()[0]
                self.assertEqual(updated.trade_date, date(2026, 6, 2))
                self.assertEqual(updated.shares, 2000)
                self.assertEqual(updated.note, "調整後")

                store.delete_portfolio_transaction(transaction_id)
                self.assertEqual(store.get_portfolio_transactions(), [])


if __name__ == "__main__":
    unittest.main()
