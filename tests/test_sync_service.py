from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.analyze.twse_calendar import is_twse_trading_day
from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    InstitutionalTrade,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.store.sqlite_store import SQLiteStore
from app.sync.service import StockSyncService, _dedupe_dividend_records


class FakeClient:
    last_warnings: list[str] = []

    def fetch_profile(self, stock_id: str) -> StockProfile:
        return StockProfile(
            stock_id=stock_id,
            name="台灣積體電路製造股份有限公司",
            short_name="台積電",
        )

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        return [
            DailyPrice(
                stock_id=stock_id,
                date=end_date,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=123,
            )
        ]

    def fetch_dividend_records(self, stock_id: str) -> list[DividendRecord]:
        return [
            DividendRecord(
                stock_id=stock_id,
                year=115,
                period="第1季",
                status="董事會決議",
                board_date=date(2026, 5, 12),
                shareholder_meeting_date=None,
                cash_dividend=7.0,
                stock_dividend=0.0,
            )
        ]

    def fetch_historical_dividend_records(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]:
        return []

    def fetch_market_valuation(self, stock_id: str) -> MarketValuation:
        return MarketValuation(
            stock_id=stock_id,
            date=date(2026, 6, 11),
            pe_ratio=30.25,
            dividend_yield=0.98,
            pb_ratio=9.9,
        )

    def fetch_monthly_revenue(self, stock_id: str) -> MonthlyRevenue:
        return MonthlyRevenue(
            stock_id=stock_id,
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
        )

    def fetch_financial_statement(self, stock_id: str) -> FinancialStatement:
        return FinancialStatement(
            stock_id=stock_id,
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
        )


class WarningClient(FakeClient):
    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        prices = super().fetch_daily_prices(stock_id, start_date, end_date)
        self.last_warnings = ["Skipped 2303 2025-08 daily prices: Cannot fetch TWSE url"]
        return prices


class PartialWarningClient(FakeClient):
    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        self.last_warnings = ["Skipped 1342 2026-06 daily prices: Cannot fetch TWSE url"]
        return [
            DailyPrice(
                stock_id=stock_id,
                date=start_date,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=123,
            )
        ]


class RecordingClient(FakeClient):
    def __init__(self) -> None:
        self.price_ranges: list[tuple[str, date, date]] = []

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        return [
            DailyPrice(
                stock_id=stock_id,
                date=end_date,
                open=101.0,
                high=102.0,
                low=100.0,
                close=101.5,
                volume=456,
            )
        ]


class TailHoleRepairClient(RecordingClient):
    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        rows: list[DailyPrice] = []
        current = start_date
        while current <= end_date:
            if is_twse_trading_day(current):
                rows.append(
                    DailyPrice(
                        stock_id=stock_id,
                        date=current,
                        open=101.0,
                        high=102.0,
                        low=100.0,
                        close=101.5,
                        volume=456,
                    )
                )
            current += timedelta(days=1)
        return rows


class MissingTargetTailClient(FakeClient):
    def __init__(self) -> None:
        self.price_ranges: list[tuple[str, date, date]] = []

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        if end_date < date(2026, 6, 30):
            return []
        return [
            DailyPrice(
                stock_id=stock_id,
                date=date(2026, 6, 30),
                open=11.1,
                high=11.25,
                low=11.05,
                close=11.2,
                volume=2001,
            )
        ]


class DividendHistoryRecordingClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.dividend_ranges: list[tuple[str, date, date]] = []

    def fetch_historical_dividend_records(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]:
        self.dividend_ranges.append((stock_id, start_date, end_date))
        return [
            DividendRecord(
                stock_id=stock_id,
                year=114,
                period="除息 06/24",
                status="除息",
                board_date=date(2025, 6, 24),
                shareholder_meeting_date=None,
                cash_dividend=2.85,
                stock_dividend=0.0,
                source="TWSE_TWT49U",
            )
        ]


class InstitutionalClient(FakeClient):
    def __init__(self) -> None:
        self.institutional_ranges: list[tuple[str, date, date, int]] = []

    def fetch_institutional_trades(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        *,
        max_days: int = 20,
        skip_dates: set[str] | None = None,
    ) -> list[InstitutionalTrade]:
        self.institutional_ranges.append((stock_id, start_date, end_date, max_days))
        return [
            InstitutionalTrade(
                stock_id=stock_id,
                date=end_date,
                foreign_net=1,
                trust_net=2,
                dealer_net=3,
                total_net=6,
            )
        ]


class StockSyncServiceTests(unittest.TestCase):
    def test_sync_stock_history_writes_profile_prices_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                service = StockSyncService(client=FakeClient(), store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2330",
                    lookback_days=7,
                    end_date=date(2026, 6, 12),
                )

                self.assertEqual(result.rows_written, 5)
                self.assertEqual(store.count_daily_prices("2330"), 1)
                self.assertEqual(store.get_profile("2330").short_name, "台積電")  # type: ignore[union-attr]
                self.assertEqual(len(store.get_dividend_records("2330")), 1)
                self.assertEqual(store.get_latest_market_valuation("2330").pe_ratio, 30.25)  # type: ignore[union-attr]
                self.assertEqual(store.get_monthly_revenues("2330")[0].year_month, "2026-05")
                self.assertEqual(store.get_latest_financial_statement("2330").eps, 22.08)  # type: ignore[union-attr]

    def test_sync_stock_history_preserves_existing_dividend_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_dividend_records(
                    [
                        DividendRecord(
                            stock_id="2330",
                            year=114,
                            period="年度",
                            status="除息",
                            board_date=None,
                            shareholder_meeting_date=None,
                            cash_dividend=12.0,
                            stock_dividend=0.0,
                            source="TWSE_TWT49U",
                        )
                    ]
                )
                service = StockSyncService(client=FakeClient(), store=store)  # type: ignore[arg-type]

                service.sync_stock_history(
                    "2330",
                    lookback_days=7,
                    end_date=date(2026, 6, 12),
                )

                periods = {(item.year, item.period) for item in store.get_dividend_records("2330")}
                self.assertIn((114, "年度"), periods)
                self.assertIn((115, "第1季"), periods)

    def test_sync_stock_history_reports_skipped_price_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                service = StockSyncService(client=WarningClient(), store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2303",
                    lookback_days=7,
                    end_date=date(2026, 6, 12),
                )

                self.assertIn("Skipped 1 price month", result.message)
                self.assertIn("2025-08", result.message)

    def test_sync_stock_history_exposes_partial_post_check_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                service = StockSyncService(client=PartialWarningClient(), store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "1342",
                    lookback_days=7,
                    end_date=date(2026, 6, 12),
                )

                self.assertEqual(result.price_warning_count, 1)
                self.assertIn("2026-06", result.first_price_warning)
                self.assertEqual(result.post_status["status"], "suspect")  # type: ignore[index]
                self.assertEqual(result.coverage["latest_date"], "2026-06-05")  # type: ignore[index]

    def test_sync_stock_history_uses_gap_plan_instead_of_full_lookback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = RecordingClient()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 18) - timedelta(days=offset),
                            open=100,
                            high=101,
                            low=99,
                            close=100,
                            volume=10,
                        )
                        for offset in range(10)
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 6, 23),
                    target_date=date(2026, 6, 22),
                )

            self.assertEqual(client.price_ranges, [("2330", date(2026, 6, 22), date(2026, 6, 22))])
            self.assertFalse(result.skipped)
            self.assertEqual(result.gap_plan["fetch_start_date"], "2026-06-22")  # type: ignore[index]
            self.assertEqual(result.coverage["status"], "patched")  # type: ignore[index]

    def test_sync_stock_history_retries_same_month_tail_when_target_day_is_sparse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = MissingTargetTailClient()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="1538",
                            date=date(2026, 6, 26),
                            open=11.7,
                            high=11.8,
                            low=11.0,
                            close=11.1,
                            volume=6700,
                        )
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "1538",
                    lookback_days=365,
                    end_date=date(2026, 6, 30),
                    target_date=date(2026, 6, 29),
                )
                latest = store.get_daily_prices("1538", limit=1)[-1]

            self.assertEqual(
                client.price_ranges,
                [
                    ("1538", date(2026, 6, 29), date(2026, 6, 29)),
                    ("1538", date(2026, 6, 29), date(2026, 6, 30)),
                ],
            )
            self.assertEqual(latest.date, date(2026, 6, 30))
            self.assertEqual(result.post_status["status"], "patched")  # type: ignore[index]
            self.assertEqual(result.coverage["status"], "patched")  # type: ignore[index]

    def test_sync_stock_history_uses_fixed_dividend_history_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = DividendHistoryRecordingClient()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 18) - timedelta(days=offset),
                            open=100,
                            high=101,
                            low=99,
                            close=100,
                            volume=10,
                        )
                        for offset in range(10)
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                service.sync_stock_history(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 6, 23),
                    target_date=date(2026, 6, 22),
                )

                periods = {(item.year, item.period) for item in store.get_dividend_records("2330")}

            self.assertEqual(client.price_ranges, [("2330", date(2026, 6, 22), date(2026, 6, 22))])
            self.assertEqual(client.dividend_ranges, [("2330", date(2021, 1, 1), date(2026, 6, 22))])
            self.assertIn((114, "除息 06/24"), periods)

    def test_sync_stock_history_defaults_weekend_target_to_previous_business_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = RecordingClient()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 18) - timedelta(days=offset),
                            open=100,
                            high=101,
                            low=99,
                            close=100,
                            volume=10,
                        )
                        # 近一年歷史都在（深度足夠），此測試只驗證週末 target 的預設行為。
                        for offset in range(400)
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 6, 21),
                )
                self.assertEqual(store.get_profile("2330").short_name, "台積電")  # type: ignore[union-attr]
                self.assertEqual(store.get_latest_market_valuation("2330").pe_ratio, 30.25)  # type: ignore[union-attr]
                self.assertEqual(store.get_monthly_revenues("2330")[0].year_month, "2026-05")
                self.assertEqual(store.get_latest_financial_statement("2330").eps, 22.08)  # type: ignore[union-attr]

            self.assertEqual(client.price_ranges, [])
            self.assertFalse(result.skipped)
            self.assertGreater(result.rows_written, 0)
            self.assertEqual(result.gap_plan["target_date"], "2026-06-18")  # type: ignore[index]

    def test_sync_stock_history_backfills_when_fresh_but_shallow(self) -> None:
        # 防回歸：STOCK_DAY_ALL top-up 讓 latest 頂到 target、但近一年只有幾筆時，
        # 手動同步不可回「已是最新」，必須整年回補。
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = RecordingClient()
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 22) - timedelta(days=offset),
                            open=100,
                            high=101,
                            low=99,
                            close=100,
                            volume=10,
                        )
                        for offset in range(5)
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 6, 23),
                    target_date=date(2026, 6, 22),
                )

        self.assertEqual(client.price_ranges, [("2330", date(2025, 6, 22), date(2026, 6, 22))])
        self.assertTrue(result.gap_plan["force_refresh_required"])  # type: ignore[index]
        self.assertEqual(result.post_status["status"], "patched")  # type: ignore[index]

    def test_sync_stock_history_backfills_profileless_market_product_short_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = RecordingClient()
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
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "00405A",
                    lookback_days=365,
                    end_date=date(2026, 7, 6),
                    target_date=date(2026, 7, 3),
                )

        self.assertEqual(client.price_ranges, [("00405A", date(2025, 7, 3), date(2026, 7, 3))])
        self.assertEqual(result.gap_plan["status"], "force_refresh_required")  # type: ignore[index]
        self.assertTrue(result.gap_plan["force_refresh_required"])  # type: ignore[index]
        self.assertEqual(result.post_status["status"], "patched")  # type: ignore[index]

    def test_sync_stock_history_repairs_recent_tail_hole_even_when_latest_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = TailHoleRepairClient()
            target = date(2026, 7, 8)
            missing_start = date(2026, 6, 23)
            missing_end = date(2026, 7, 6)
            rows: list[DailyPrice] = []
            current = date(2025, 7, 7)
            while current <= target:
                if is_twse_trading_day(current) and not (missing_start <= current <= missing_end):
                    rows.append(DailyPrice("2330", current, 100, 101, 99, 100, 10))
                current += timedelta(days=1)

            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(rows)
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_stock_history(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 7, 9),
                    target_date=target,
                )
                repaired = store.compute_data_coverage(
                    "2330",
                    "daily_price",
                    target_date=target,
                )

        self.assertEqual(client.price_ranges, [("2330", missing_start, target)])
        self.assertEqual(result.gap_plan["status"], "gap")  # type: ignore[index]
        self.assertEqual(result.gap_plan["fetch_start_date"], missing_start.isoformat())  # type: ignore[index]
        self.assertEqual(result.post_status["status"], "patched")  # type: ignore[index]
        self.assertEqual(repaired["tail_hole_count"], 0)

    def test_sync_institutional_uses_gap_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            client = InstitutionalClient()
            with SQLiteStore(db_path) as store:
                store.upsert_institutional_trades(
                    [
                        InstitutionalTrade(
                            stock_id="2330",
                            date=date(2026, 6, 18),
                            foreign_net=1,
                            trust_net=0,
                            dealer_net=0,
                            total_net=1,
                        )
                    ]
                )
                service = StockSyncService(client=client, store=store)  # type: ignore[arg-type]
                result = service.sync_institutional(
                    "2330",
                    lookback_days=365,
                    end_date=date(2026, 6, 23),
                    target_date=date(2026, 6, 22),
                )

            self.assertEqual(
                client.institutional_ranges,
                [("2330", date(2026, 6, 22), date(2026, 6, 22), 20)],
            )
            self.assertFalse(result.skipped)
            self.assertEqual(result.coverage["status"], "patched")  # type: ignore[index]

    def test_dedupe_dividend_records_keeps_unpaid_quarter_and_drops_paid_duplicate(self) -> None:
        records = [
            DividendRecord(
                stock_id="2330",
                year=115,
                period="除息 03/17",
                status="除息",
                board_date=date(2026, 3, 17),
                shareholder_meeting_date=None,
                cash_dividend=6.000035,
                stock_dividend=0.0,
                source="TWSE_TWT49U",
            ),
            DividendRecord(
                stock_id="2330",
                year=115,
                period="除息 06/11",
                status="除息",
                board_date=date(2026, 6, 11),
                shareholder_meeting_date=None,
                cash_dividend=6.000035,
                stock_dividend=0.0,
                source="TWSE_TWT49U",
            ),
            DividendRecord(
                stock_id="2330",
                year=115,
                period="第4季",
                status="董事會決議",
                board_date=date(2026, 2, 10),
                shareholder_meeting_date=None,
                cash_dividend=6.00003573,
                stock_dividend=0.0,
                source="TWSE_T187AP45",
            ),
            DividendRecord(
                stock_id="2330",
                year=115,
                period="第1季",
                status="董事會決議",
                board_date=date(2026, 5, 12),
                shareholder_meeting_date=None,
                cash_dividend=7.0,
                stock_dividend=0.0,
                source="TWSE_T187AP45",
            ),
        ]

        deduped = _dedupe_dividend_records(records)

        self.assertEqual(sum(item.cash_dividend for item in deduped), 19.00007)
        self.assertEqual({item.period for item in deduped}, {"除息 03/17", "除息 06/11", "第1季"})


if __name__ == "__main__":
    unittest.main()
