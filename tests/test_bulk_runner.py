from __future__ import annotations

import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.models import DailyPrice, DividendRecord, InstitutionalTrade, StockProfile
from app.sync.bulk_runner import (
    BULK_RUN_KEY,
    BULK_STATUS_HISTORY_PENDING,
    BULK_STATUS_UNSUPPORTED_HISTORY,
    build_bulk_plan,
)


class FixedDate(date):
    @classmethod
    def today(cls) -> "FixedDate":
        return cls(2026, 2, 23)


class June30Date(date):
    @classmethod
    def today(cls) -> "June30Date":
        return cls(2026, 6, 30)


class July1Date(date):
    @classmethod
    def today(cls) -> "July1Date":
        return cls(2026, 7, 1)


# today = 2026-02-23（農曆年後第一個交易日）。2/12~2/22 為春節連假＋週末（全休市），
# 因此「今天之前的最後一個交易日」= 2026-02-11。新版 target_date 就是它。
EXPECTED_TARGET = date(2026, 2, 11)


class FakeBulkClient:
    def __init__(self, *, request_interval: float = 0.0) -> None:
        self.request_interval = request_interval
        self.historical_dividend_ranges: list[tuple[date, date]] = []
        self.t86_dates: list[date] = []
        self.price_ranges: list[tuple[str, date, date]] = []
        self.daily_last_date: date | None = None
        self.latest_all_calls = 0
        self.latest_all_prices = [DailyPrice("2330", EXPECTED_TARGET, 10, 11, 9, 10, 1000)]

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
        self.price_ranges.append((stock_id, start_date, end_date))
        last = self.daily_last_date or end_date
        if (end_date - start_date).days > 90 and self.daily_last_date is None:
            return [
                DailyPrice(stock_id, end_date - timedelta(days=offset), 10, 11, 9, 10, 1000)
                for offset in range(180)
            ]
        return [DailyPrice(stock_id, last, 10, 11, 9, 10, 1000)]

    def fetch_latest_all_prices(self) -> list[DailyPrice]:
        self.latest_all_calls += 1
        return list(self.latest_all_prices)


class ListedProfileBulkClient(FakeBulkClient):
    """上市日很近的新股（2026-02-09 上市，target=2026-02-11）。"""

    def fetch_listed_profiles(self) -> list[StockProfile]:
        return [
            StockProfile(
                stock_id="2330",
                name="台積電",
                short_name="台積電",
                listed_date=date(2026, 2, 9),
            )
        ]

    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        return [
            DailyPrice(stock_id, day, 10, 11, 9, 10, 1000)
            for day in (date(2026, 2, 9), date(2026, 2, 10), date(2026, 2, 11))
            if start_date <= day <= end_date
        ]


class MultiProfileBulkClient(FakeBulkClient):
    def fetch_listed_profiles(self) -> list[StockProfile]:
        return [
            StockProfile(stock_id="3003", name="淺歷史", short_name="淺歷史"),
            StockProfile(stock_id="1001", name="已完整", short_name="已完整"),
            StockProfile(stock_id="4004", name="空資料", short_name="空資料"),
            StockProfile(stock_id="5005", name="大缺口", short_name="大缺口"),
            StockProfile(stock_id="2002", name="只缺一天", short_name="只缺一天"),
        ]


class MissingTargetTailBulkClient(FakeBulkClient):
    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        if end_date < date(2026, 6, 30):
            return []
        return [DailyPrice(stock_id, date(2026, 6, 30), 11.1, 11.25, 11.05, 11.2, 2001)]


class ProgressiveMonthsBulkClient(FakeBulkClient):
    """支援 on_month 的 client：回兩個月資料，逐月回呼；可設定第二月拋錯。"""

    def __init__(self, *, request_interval: float = 0.0, fail_second_month: bool = False) -> None:
        super().__init__(request_interval=request_interval)
        self.fail_second_month = fail_second_month
        self.month_batches: list[list[DailyPrice]] = []

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        *,
        on_month=None,
    ) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        newest = [DailyPrice(stock_id, date(2026, 2, 11), 10, 11, 9, 10, 1000)]
        older = [DailyPrice(stock_id, date(2026, 1, 15), 10, 11, 9, 10, 1000)]
        out: list[DailyPrice] = []
        for batch in (newest, older):
            if batch is older and self.fail_second_month:
                raise RuntimeError("simulated disconnect during backfill")
            out.extend(batch)
            self.month_batches.append(batch)
            if on_month is not None:
                on_month(batch)
        return sorted(out, key=lambda item: item.date)


class UnsupportedHistoryBulkClient(FakeBulkClient):
    """受益證券/ETN 情境：STOCK_DAY 整窗回空、無 warning。"""

    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        self.last_warnings = []
        return []


class EmptyNoWarningBulkClient(FakeBulkClient):
    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        self.last_warnings = []
        return []


class WarningEmptyBulkClient(FakeBulkClient):
    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.price_ranges.append((stock_id, start_date, end_date))
        self.last_warnings = [f"Skipped {stock_id} {start_date:%Y-%m} daily prices after retry: timeout"]
        return []


class FakeBulkStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.dividends: list[DividendRecord] = []
        self.bulk_marks: list[tuple[str, str, str, str]] = []
        self.coverage_refreshes: list[tuple[str, str, date | None]] = []
        self.daily: dict[str, list[DailyPrice]] = {}
        self.coverage_overrides: dict[str, dict[str, object]] = {}
        self.json_cache_deletes: list[str] = []
        self.bulk_details: dict[tuple[str, str, str], dict[str, object]] = {}

    def upsert_profiles(self, profiles: list[StockProfile]) -> int:
        return len(profiles)

    def ensure_bulk_items(self, run_key: str, item_type: str, item_keys: list[str]) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        for key in item_keys:
            self.bulk_details.setdefault(
                (run_key, item_type, str(key)),
                {"item_key": str(key), "status": "pending", "error": "", "updated_at": now},
            )
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

    def get_bulk_item(self, run_key: str, item_type: str, item_key: str) -> dict[str, object] | None:
        return self.bulk_details.get((run_key, item_type, item_key))

    def get_bulk_item_keys_by_status(self, run_key: str, item_type: str, status: str) -> list[str]:
        return [
            item_key
            for mark_run_key, mark_item_type, item_key, mark_status in self.bulk_marks
            if mark_run_key == run_key and mark_item_type == item_type and mark_status == status
        ]

    def mark_bulk_item(
        self,
        run_key: str,
        item_type: str,
        item_key: str,
        status: str,
        error: str = "",
    ) -> None:
        self.bulk_marks.append((run_key, item_type, item_key, status))
        self.bulk_details[(run_key, item_type, item_key)] = {
            "item_key": item_key,
            "status": status,
            "error": error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def upsert_institutional_trades(self, trades: list[InstitutionalTrade]) -> int:
        return len(trades)

    def upsert_daily_prices(self, prices: list[DailyPrice]) -> int:
        rows = list(prices)
        for price in rows:
            self.daily.setdefault(price.stock_id, []).append(price)
        return len(rows)

    def get_daily_prices(
        self,
        stock_id: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[DailyPrice]:
        rows = sorted(self.daily.get(stock_id, []), key=lambda p: p.date)
        if limit is not None:
            rows = rows[-limit:]
        return rows

    def get_price_stock_ids(self) -> set[str]:
        return set(self.daily)

    def has_non_topup_daily_price(self, stock_id: str) -> bool:
        return any(
            (price.source or "") != "TWSE_STOCK_DAY_ALL"
            for price in self.daily.get(stock_id, [])
        )

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
        latest = self.get_daily_prices(stock_id, limit=1)
        coverage = {
            "stock_id": stock_id,
            "node": node,
            "latest_date": latest[-1].date.isoformat() if latest else None,
            "row_count": len(self.get_daily_prices(stock_id)),
            "hole_count": 0,
            "target_date": target_date.isoformat() if target_date else None,
            "status": status or "indexed",
        }
        coverage.update(self.coverage_overrides.get(stock_id, {}))
        return coverage

    def compute_data_coverage(
        self,
        stock_id: str,
        node: str,
        *,
        target_date: date | None = None,
        status: str | None = None,
        suspect_reason: str = "",
    ) -> dict[str, object]:
        return self.refresh_data_coverage(
            stock_id,
            node,
            target_date=target_date,
            status=status,
            suspect_reason=suspect_reason,
        )

    def delete_json_cache(self, key: str) -> None:
        self.json_cache_deletes.append(key)


def _statuses_for(store: FakeBulkStore, sid: str) -> list[str]:
    return [mark[3] for mark in store.bulk_marks if mark[1] == "stock" and mark[2] == sid]


def _history_rows(stock_id: str, latest: date, count: int = 180) -> list[DailyPrice]:
    return [
        DailyPrice(stock_id, latest - timedelta(days=offset), 10, 11, 9, 10, 1000)
        for offset in range(count)
    ]


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

    def test_sync_one_refreshes_daily_coverage_and_marks_done_when_current(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        self.assertEqual(
            fake_store.coverage_refreshes,
            [
                ("2330", "daily_price", EXPECTED_TARGET),
                ("2330", "daily_price", EXPECTED_TARGET),
            ],
        )
        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_prelude_prioritizes_small_gaps_before_history_backfill(self) -> None:
        fake_client = MultiProfileBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["1001"] = _history_rows("1001", EXPECTED_TARGET, count=180)
        fake_store.daily["2002"] = _history_rows("2002", date(2026, 2, 10), count=180)
        fake_store.daily["3003"] = _history_rows("3003", EXPECTED_TARGET, count=10)
        fake_store.daily["5005"] = _history_rows("5005", date(2025, 9, 1), count=180)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]

        self.assertEqual(
            plan.list_stocks(),
            ["2002", "5005", "3003", "4004", "1001"],
        )

    def test_quiet_mode_prioritizes_freshness_gaps_before_history_depth(self) -> None:
        # 背景慢補也不能讓「只差一天」卡在整批歷史回補後面。
        fake_client = MultiProfileBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["1001"] = _history_rows("1001", EXPECTED_TARGET, count=180)
        fake_store.daily["2002"] = _history_rows("2002", date(2026, 2, 10), count=180)
        fake_store.daily["3003"] = _history_rows("3003", EXPECTED_TARGET, count=10)
        fake_store.daily["5005"] = _history_rows("5005", date(2025, 9, 1), count=180)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, quiet=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]

        self.assertEqual(
            plan.list_stocks(),
            ["2002", "5005", "3003", "4004"],
        )

    def test_recent_failed_stock_is_deferred_until_backoff_expires(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.mark_bulk_item(BULK_RUN_KEY, "stock", "2330", "failed", error="TWSE timeout")
        fake_store.mark_bulk_item(BULK_RUN_KEY, "stock", "2317", "failed", error="older timeout")
        fake_store.bulk_details[(BULK_RUN_KEY, "stock", "2317")]["updated_at"] = (
            datetime.now() - timedelta(hours=1)
        ).isoformat(timespec="seconds")

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertTrue(plan.skip("2330"))

            retry_plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, retry_failed_only=True)
            retry_plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertEqual(retry_plan.list_stocks(), ["2317"])

    def test_sync_one_patches_only_missing_daily_gap_when_small(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", date(2026, 2, 10))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [("2330", EXPECTED_TARGET, EXPECTED_TARGET)])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_prelude_latest_all_topup_lets_one_day_gap_skip_without_month_fetch(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = [DailyPrice("2330", EXPECTED_TARGET, 10, 11, 9, 10, 1000)]
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", date(2026, 2, 10))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertTrue(plan.skip("2330"))

        self.assertEqual(fake_client.latest_all_calls, 1)
        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_manual_latest_all_single_row_defers_history_backfill(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = [DailyPrice("2330", EXPECTED_TARGET, 10, 11, 9, 10, 1000)]
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertTrue(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], BULK_STATUS_HISTORY_PENDING)

    def test_sync_one_retries_same_month_tail_when_target_day_is_sparse(self) -> None:
        fake_client = MissingTargetTailBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", date(2026, 6, 26))

        with (
            patch("app.sync.bulk_runner.date", June30Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        self.assertEqual(
            fake_client.price_ranges,
            [
                ("2330", date(2026, 6, 29), date(2026, 6, 29)),
                ("2330", date(2026, 6, 29), date(2026, 6, 30)),
            ],
        )
        self.assertEqual(fake_store.daily["2330"][-1].date, date(2026, 6, 30))
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_sync_one_marks_short_latest_gap_as_source_pending_not_failed(self) -> None:
        fake_client = EmptyNoWarningBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = [DailyPrice("2330", date(2026, 6, 29), 10, 11, 9, 10, 1000)]

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        statuses = _statuses_for(fake_store, "2330")
        self.assertEqual(statuses[-1], "source_pending")
        self.assertNotIn("failed", statuses)

    def test_recent_source_pending_stock_waits_before_retrying_source(self) -> None:
        fake_client = EmptyNoWarningBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = [DailyPrice("2330", date(2026, 6, 29), 10, 11, 9, 10, 1000)]

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            fake_store.mark_bulk_item(BULK_RUN_KEY, "stock", "2330", "source_pending", error="not published")
            self.assertTrue(plan.skip("2330"))
            fake_store.bulk_details[(BULK_RUN_KEY, "stock", "2330")]["updated_at"] = (
                datetime.now() - timedelta(hours=2)
            ).isoformat(timespec="seconds")
            self.assertFalse(plan.skip("2330"))

    def test_sync_one_turns_twse_warnings_into_retryable_failure(self) -> None:
        fake_client = WarningEmptyBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = [DailyPrice("2330", date(2026, 6, 29), 10, 11, 9, 10, 1000)]

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            with self.assertRaisesRegex(RuntimeError, "TWSE 抓取不穩"):
                plan.sync_one("2330")

        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "failed")

    def test_retry_failed_marks_done_when_single_sync_already_caught_up(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.bulk_marks.append((BULK_RUN_KEY, "stock", "2330", "failed"))
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, retry_failed_only=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertEqual(plan.list_stocks(), ["2330"])
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_sync_one_marks_failed_when_still_behind_target(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_client.daily_last_date = date(2026, 1, 5)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        statuses = _statuses_for(fake_store, "2330")
        self.assertEqual(statuses[-1], "failed")
        self.assertNotIn("done", statuses)

    def test_skip_refetches_stale_stock_even_if_previously_done(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]

            fake_store.daily["1101"] = [DailyPrice("1101", date(2026, 1, 5), 10, 11, 9, 10, 1000)]
            fake_store.bulk_marks.append(("full_market", "stock", "1101", "done"))
            self.assertFalse(plan.skip("1101"))

            fake_store.daily["2454"] = _history_rows("2454", date(2026, 2, 23))
            self.assertTrue(plan.skip("2454"))

            self.assertFalse(plan.skip("9999"))

    def test_on_finish_tops_up_latest_and_refreshes_radar_snapshot(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
            patch("app.screener.value.refresh_value_screener") as mock_refresh,
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.on_finish({})

        self.assertEqual(fake_client.latest_all_calls, 2)
        self.assertTrue(fake_store.daily.get("2330"))
        self.assertEqual(fake_store.daily["2330"][-1].date, EXPECTED_TARGET)
        mock_refresh.assert_called_once()
        self.assertIn("local_data_v3", fake_store.json_cache_deletes)

    def test_new_listing_with_history_since_listing_skips(self) -> None:
        # 新上市股只有上市以來的 3 筆 → 深度以上市日推導為「完整」→ 跳過，不再 ping-pong 重抓。
        fake_client = ListedProfileBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = [
            DailyPrice("2330", date(2026, 2, 9), 10, 11, 9, 10, 1000),
            DailyPrice("2330", date(2026, 2, 10), 10, 11, 9, 10, 1000),
            DailyPrice("2330", date(2026, 2, 11), 10, 11, 9, 10, 1000),
        ]

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertTrue(plan.skip("2330"))

        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_new_listing_backfill_starts_at_listed_date(self) -> None:
        # 新上市股完全沒資料 → 回補起點是上市日，不是 target-365（省掉 12 個月空請求）。
        fake_client = ListedProfileBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertFalse(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [("2330", date(2026, 2, 9), EXPECTED_TARGET)])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_manual_accumulated_topup_rows_defer_history_backfill(self) -> None:
        # 防回歸：受災股被每日 top-up 累到 10 筆（> 舊門檻 5）且 latest 頂到 target，
        # 舊常數門檻會判 current → 永遠跳過。現在手動全市場不當場補整年，
        # 但也不能標 done；要留下 history_pending 讓背景/單檔補歷史。
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET, count=10)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertTrue(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], BULK_STATUS_HISTORY_PENDING)

    def test_quiet_mode_backfills_fresh_but_shallow_history(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET, count=10)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, quiet=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertFalse(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [("2330", date(2025, 2, 11), EXPECTED_TARGET)])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_manual_history_backfill_mode_backfills_fresh_but_shallow_history(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET, count=10)

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(
                Path("fake.sqlite3"),
                request_interval=0,
                include_history_backfill=True,
            )
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertEqual(plan.mode, "history")
            self.assertFalse(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [("2330", date(2025, 2, 11), EXPECTED_TARGET)])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_bulk_sync_does_not_mark_done_when_recent_tail_hole_remains(self) -> None:
        fake_client = EmptyNoWarningBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        target = date(2026, 6, 30)
        fake_store.daily["2330"] = _history_rows("2330", target, count=180)
        fake_store.coverage_overrides["2330"] = {
            "horizon_row_count": 180,
            "tail_hole_count": 5,
            "tail_gap_start_date": "2026-06-23",
            "tail_gap_end_date": "2026-06-29",
        }

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertFalse(plan.skip("2330"))
            plan.sync_one("2330")

        self.assertEqual(fake_client.price_ranges, [("2330", date(2026, 6, 23), target)])
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "failed")
        self.assertIn("日線尾端仍有缺洞", fake_store.bulk_details[("full_market", "stock", "2330")]["error"])

    def test_quiet_mode_includes_profileless_market_products_from_latest_topup(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.latest_all_prices = [
            DailyPrice("00939", EXPECTED_TARGET, 10, 11, 9, 10, 1000)
        ]
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, quiet=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            self.assertIn("00939", plan.list_stocks())
            plan.sync_one("00939")

        self.assertEqual(fake_client.price_ranges, [("00939", date(2025, 2, 11), EXPECTED_TARGET)])
        self.assertEqual(_statuses_for(fake_store, "00939")[-1], "done")

    def test_prelude_does_not_mark_empty_t86_dates_done(self) -> None:
        # 防回歸：T86 某天回空(尚未公布)時不可標 done，否則會被永久跳過 → 全市場「法人缺 N 日」補不回。
        fake_client = FakeBulkClient(request_interval=0)
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]

        t86_done = {m[2] for m in fake_store.bulk_marks if m[1] == "t86_date" and m[3] == "done"}
        self.assertIn("2026-02-11", t86_done)       # 有資料 → done
        self.assertNotIn("2026-02-23", t86_done)    # 回空 → 不可 done（要能下次重抓）


if __name__ == "__main__":
    unittest.main()


class UnsupportedHistoryTests(unittest.TestCase):
    """受益證券/ETN：來源查無歷史 → 標 unsupported_history、不進 failed、長冷卻。"""

    def _etn_store(self) -> FakeBulkStore:
        store = FakeBulkStore(Path("fake.sqlite3"))
        # 本地資料全部來自 STOCK_DAY_ALL top-up（最新已到 target、歷史極淺）。
        store.daily["020039"] = [
            DailyPrice("020039", EXPECTED_TARGET - timedelta(days=1), 10, 11, 9, 10, 1000, source="TWSE_STOCK_DAY_ALL"),
            DailyPrice("020039", EXPECTED_TARGET, 10, 11, 9, 10, 1000, source="TWSE_STOCK_DAY_ALL"),
        ]
        return store

    def test_empty_fetch_with_topup_only_history_marks_unsupported_history(self) -> None:
        fake_client = UnsupportedHistoryBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = self._etn_store()

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, include_history_backfill=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("020039")

        statuses = _statuses_for(fake_store, "020039")
        self.assertEqual(statuses[-1], BULK_STATUS_UNSUPPORTED_HISTORY)
        self.assertNotIn("failed", statuses)
        detail = fake_store.bulk_details[(BULK_RUN_KEY, "stock", "020039")]
        self.assertIn("受益證券/ETN", str(detail["error"]))

    def test_empty_fetch_with_real_history_still_fails(self) -> None:
        """本地曾有 STOCK_DAY 歷史 → 整窗回空是來源異常，照舊 failed 可重試。"""
        fake_client = EmptyNoWarningBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        target = date(2026, 6, 30)
        fake_store.daily["2330"] = _history_rows("2330", target, count=180)
        fake_store.coverage_overrides["2330"] = {
            "horizon_row_count": 180,
            "tail_hole_count": 5,
            "tail_gap_start_date": "2026-06-23",
            "tail_gap_end_date": "2026-06-29",
        }

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "failed")

    def test_unsupported_history_cooldown_skips_then_expires(self) -> None:
        fake_client = UnsupportedHistoryBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = self._etn_store()

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, include_history_backfill=True)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            fake_store.mark_bulk_item(
                BULK_RUN_KEY, "stock", "020039", BULK_STATUS_UNSUPPORTED_HISTORY, error="來源無歷史"
            )
            # 冷卻中（剛標記）：skip 不重抓
            self.assertTrue(plan.skip("020039"))
            self.assertEqual(fake_client.price_ranges, [])
            # 冷卻過期（8 天前標記）：重新檢查
            fake_store.bulk_details[(BULK_RUN_KEY, "stock", "020039")]["updated_at"] = (
                datetime.now() - timedelta(days=8)
            ).isoformat(timespec="seconds")
            self.assertFalse(plan.skip("020039"))

    def test_short_gap_without_history_still_prefers_source_pending(self) -> None:
        """缺 1~2 天且來源回空：即使本地全是 top-up，也先當「等來源」不誤標無歷史。"""
        fake_client = UnsupportedHistoryBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        fake_store.daily["2330"] = [
            DailyPrice("2330", date(2026, 6, 29), 10, 11, 9, 10, 1000, source="TWSE_STOCK_DAY_ALL")
            for _ in range(1)
        ]
        fake_store.coverage_overrides["2330"] = {"horizon_row_count": 200}

        with (
            patch("app.sync.bulk_runner.date", July1Date),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        statuses = _statuses_for(fake_store, "2330")
        self.assertEqual(statuses[-1], "source_pending")
        self.assertNotIn(BULK_STATUS_UNSUPPORTED_HISTORY, statuses)


class ProgressiveWriteTests(unittest.TestCase):
    """逐月漸進寫入：支援 on_month 的 client 逐月落庫；中斷時已抓月份保留。"""

    def test_progressive_client_persists_month_by_month(self) -> None:
        fake_client = ProgressiveMonthsBulkClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        # 寫入後 coverage 視為夠深，讓驗收聚焦「逐月寫入」而不是歷史深度。
        fake_store.coverage_overrides["2330"] = {"horizon_row_count": 200}

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            plan.sync_one("2330")

        # 兩個月都寫進 store（經由 on_month 回呼，而不是最後一次性）
        self.assertEqual(len(fake_client.month_batches), 2)
        dates = sorted(price.date for price in fake_store.daily["2330"])
        self.assertIn(date(2026, 1, 15), dates)
        self.assertIn(date(2026, 2, 11), dates)
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "done")

    def test_interrupted_backfill_keeps_already_fetched_months(self) -> None:
        fake_client = ProgressiveMonthsBulkClient(request_interval=0, fail_second_month=True)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            with self.assertRaisesRegex(RuntimeError, "simulated disconnect"):
                plan.sync_one("2330")

        # 第一個月（最新月）已寫入，不因中斷而白抓
        dates = [price.date for price in fake_store.daily.get("2330", [])]
        self.assertIn(date(2026, 2, 11), dates)
        self.assertEqual(_statuses_for(fake_store, "2330")[-1], "failed")


class ExtraStatusTests(unittest.TestCase):
    """限流可見化：plan.extra_status 回報 TWSE 自適應限流倍數。"""

    def test_extra_status_reports_throttle_factor(self) -> None:
        fake_client = FakeBulkClient(request_interval=0)
        fake_client.throttle_factor = lambda: 4.0  # type: ignore[attr-defined]
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with (
            patch("app.sync.bulk_runner.date", FixedDate),
            patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
            patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
        ):
            plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0)
            self.assertEqual(plan.extra_status(), {})  # prelude 前沒有 client
            plan.prelude(threading.Event())  # type: ignore[union-attr]
            payload = plan.extra_status()

        self.assertEqual(payload["throttle_factor"], 4.0)
        self.assertTrue(payload["throttled"])
