from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
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
