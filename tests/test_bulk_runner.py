from __future__ import annotations

import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.models import DailyPrice, DividendRecord, InstitutionalTrade, StockProfile
from app.sync.bulk_runner import build_bulk_plan


class FixedDate(date):
    @classmethod
    def today(cls) -> "FixedDate":
        return cls(2026, 2, 23)


class FakeBulkClient:
    def __init__(self, *, request_interval: float = 0.0) -> None:
        self.request_interval = request_interval
        self.historical_dividend_ranges: list[tuple[date, date]] = []
        self.t86_dates: list[date] = []

    def fetch_listed_profiles(self) -> list[StockProfile]:
        return [StockProfile(stock_id="2330", name="台積電", short_name="台積電")]

    def fetch_all_monthly_revenues(self) -> list[object]:
        return []

    def fetch_all_market_valuations(self) -> list[object]:
        return []

    def fetch_all_financial_statements(self) -> list[object]:
        return []

    def fetch_all_dividend_records(self) -> list[DividendRecord]:
        return [
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

    def fetch_all_historical_dividend_records(
        self, start_date: date, end_date: date
    ) -> list[DividendRecord]:
        self.historical_dividend_ranges.append((start_date, end_date))
        return [
            DividendRecord(
                stock_id="2330",
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

    def fetch_institutional_trades_for_date(self, day: date) -> list[InstitutionalTrade]:
        self.t86_dates.append(day)
        if day == date(2026, 2, 11):
            return [
                InstitutionalTrade(
                    stock_id="2330",
                    date=day,
                    foreign_net=1,
                    trust_net=0,
                    dealer_net=0,
                    total_net=1,
                )
            ]
        return []

    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        return [DailyPrice(stock_id, end_date, 10, 11, 9, 10, 1000)]


class FakeBulkStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.dividends: list[DividendRecord] = []
        self.bulk_marks: list[tuple[str, str, str, str]] = []
        self.coverage_refreshes: list[tuple[str, str, date | None]] = []

    def upsert_profiles(self, profiles: list[StockProfile]) -> int:
        return len(profiles)

    def ensure_bulk_items(self, run_key: str, item_type: str, item_keys: list[str]) -> int:
        return len(item_keys)

    def upsert_monthly_revenues(self, rows: list[object]) -> int:
        return len(rows)

    def upsert_market_valuations(self, rows: list[object]) -> int:
        return len(rows)

    def upsert_financial_statements(self, rows: list[object]) -> int:
        return len(rows)

    def upsert_dividend_records(self, records: list[DividendRecord]) -> int:
        self.dividends.extend(records)
        return len(records)

    def get_institutional_dates_any(self) -> set[str]:
        return set()

    def get_bulk_item_statuses(self, run_key: str, item_type: str) -> dict[str, str]:
        return {}

    def mark_bulk_item(
        self,
        run_key: str,
        item_type: str,
        item_key: str,
        status: str,
        error: str = "",
    ) -> None:
        self.bulk_marks.append((run_key, item_type, item_key, status))

    def upsert_institutional_trades(self, trades: list[InstitutionalTrade]) -> int:
        return len(trades)

    def upsert_daily_prices(self, prices: list[DailyPrice]) -> int:
        return len(prices)

    def refresh_data_coverage(
        self,
        stock_id: str,
        node: str,
        *,
        target_date: date | None = None,
        status: str | None = None,
        suspect_reason: str = "",
    ) -> dict[str, object]:
        self.coverage_refreshes.append((stock_id, node, target_date))
        return {}


class BulkRunnerTests(unittest.TestCase):
    def test_prelude_backfills_dividend_history_and_skips_twse_holidays(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            self.assertIsNotNone(plan.prelude)
            plan.prelude(threading.Event())  # type: ignore[union-attr]

        self.assertEqual(fake_client.historical_dividend_ranges, [(date(2021, 1, 1), date(2026, 2, 23))])
        self.assertEqual({item.period for item in fake_store.dividends}, {"第1季", "除息 06/24"})
        self.assertEqual(fake_client.t86_dates[:2], [date(2026, 2, 23), date(2026, 2, 11)])
        self.assertNotIn(date(2026, 2, 12), fake_client.t86_dates)

    def test_sync_one_refreshes_daily_coverage_after_price_write(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        self.assertEqual(fake_store.coverage_refreshes, [("2330", "daily_price", date(2026, 2, 23))])


if __name__ == "__main__":
    unittest.main()
