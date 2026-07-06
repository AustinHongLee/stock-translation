from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.models import DailyPrice, StockProfile
from app.store.sqlite_store import SQLiteStore
from app.sync.bulk import BulkDownloadManager, BulkPlan
from app.sync.bulk_runner import QUIET_REQUEST_INTERVAL, build_bulk_plan
from app.sync.twse import TwseClient
from app.web.server import (
    QUIET_SYNC_STATE_KEY,
    _bulk_blocks_twse_fetch,
    _preempt_quiet_run,
    _quiet_sync_due,
)

try:
    from tests.test_bulk_runner import (
        EXPECTED_TARGET,
        FakeBulkClient,
        FakeBulkStore,
        FixedDate,
        _history_rows,
    )
except ImportError:  # unittest discover -s tests 以頂層模組名匯入
    from test_bulk_runner import (  # type: ignore[no-redef]
        EXPECTED_TARGET,
        FakeBulkClient,
        FakeBulkStore,
        FixedDate,
        _history_rows,
    )


class MultiProfileQuietClient(FakeBulkClient):
    """三檔股票 + 記錄重型共用檔抓取次數（quiet 模式必須為 0）。"""

    def __init__(self, *, request_interval: float = 0.0) -> None:
        super().__init__(request_interval=request_interval)
        self.heavy_calls = 0

    def fetch_listed_profiles(self) -> list[StockProfile]:
        return [
            StockProfile(stock_id="2330", name="台積電", short_name="台積電"),
            StockProfile(stock_id="1101", name="台泥", short_name="台泥"),
            StockProfile(stock_id="9999", name="測試", short_name="測試"),
        ]

    def fetch_all_monthly_revenues(self) -> list[object]:
        self.heavy_calls += 1
        return []

    def fetch_all_market_valuations(self) -> list[object]:
        self.heavy_calls += 1
        return []

    def fetch_all_financial_statements(self) -> list[object]:
        self.heavy_calls += 1
        return []

    def fetch_all_dividend_records(self):  # noqa: ANN201
        self.heavy_calls += 1
        return []

    def fetch_all_historical_dividend_records(self, start_date, end_date):  # noqa: ANN001, ANN201
        self.heavy_calls += 1
        return []


def _quiet_plan(fake_client, fake_store, **kwargs):
    with (
        patch("app.sync.bulk_runner.date", FixedDate),
        patch("app.sync.bulk_runner.TwseClient", return_value=fake_client),
        patch("app.sync.bulk_runner.SQLiteStore", return_value=fake_store),
    ):
        plan = build_bulk_plan(Path("fake.sqlite3"), request_interval=0, quiet=True, **kwargs)
        plan.prelude(threading.Event())  # type: ignore[union-attr]
        return plan


class QuietPlanTests(unittest.TestCase):
    def test_quiet_prelude_skips_heavy_shared_fetches(self) -> None:
        fake_client = MultiProfileQuietClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        plan = _quiet_plan(fake_client, fake_store)

        self.assertEqual(plan.mode, "quiet")
        self.assertEqual(fake_client.heavy_calls, 0)
        # 只補「缺的」近日 T86：本地無任何法人資料 → 檢查近幾個交易日，
        # 只有 2026-02-11 有資料 → 只有那天標 done。
        self.assertIn(date(2026, 2, 11), fake_client.t86_dates)
        t86_done = {m[2] for m in fake_store.bulk_marks if m[1] == "t86_date" and m[3] == "done"}
        self.assertEqual(t86_done, {"2026-02-11"})

    def test_quiet_list_targets_shallowest_first_with_cap(self) -> None:
        fake_client = MultiProfileQuietClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))
        # 2330：假最新（只有 10 筆但頂到 target）→ 需要補，ratio 低。
        fake_store.daily["2330"] = _history_rows("2330", EXPECTED_TARGET, count=10)
        # 1101：整年都在 → current，不入列。
        fake_store.daily["1101"] = _history_rows("1101", EXPECTED_TARGET, count=180)
        # 9999：完全沒資料 → 最缺，排第一。

        plan = _quiet_plan(fake_client, fake_store)
        self.assertEqual(plan.list_stocks(), ["9999", "2330"])

        plan_capped = _quiet_plan(fake_client, fake_store, quiet_max_stocks=1)
        self.assertEqual(plan_capped.list_stocks(), ["9999"])

    def test_quiet_on_finish_is_light(self) -> None:
        fake_client = MultiProfileQuietClient(request_interval=0)
        fake_client.latest_all_prices = []
        fake_store = FakeBulkStore(Path("fake.sqlite3"))

        with patch("app.screener.value.refresh_value_screener") as mock_refresh:
            plan = _quiet_plan(fake_client, fake_store)
            plan.on_finish({})  # type: ignore[misc]

        self.assertEqual(fake_client.latest_all_calls, 1)  # 只有 prelude 的一次 top-up
        mock_refresh.assert_not_called()
        self.assertIn("local_data_v3", fake_store.json_cache_deletes)


class ThrottleTests(unittest.TestCase):
    def test_throttle_factor_doubles_on_failure_and_recovers(self) -> None:
        client = TwseClient(request_interval=0)
        self.assertEqual(client.throttle_factor(), 1.0)
        for _ in range(10):
            client._register_failure()
        self.assertEqual(client.throttle_factor(), TwseClient.THROTTLE_FACTOR_MAX)
        for _ in range(10):
            client._register_success()
        self.assertEqual(client.throttle_factor(), 1.0)

    def test_sleep_between_requests_is_noop_when_interval_zero(self) -> None:
        client = TwseClient(request_interval=0)
        client._register_failure()
        client._sleep_between_requests()  # 不應 sleep、不應丟例外
        client._sleep_between_requests(minimum=5.0)


class ManagerModeTests(unittest.TestCase):
    def test_manager_records_plan_mode(self) -> None:
        manager = BulkDownloadManager()
        self.assertEqual(manager.status().get("mode"), "manual")
        plan = BulkPlan(list_stocks=lambda: [], sync_one=lambda sid: None, mode="quiet")
        manager.start(plan)
        manager.join(5)
        status = manager.status()
        self.assertEqual(status.get("mode"), "quiet")
        self.assertEqual(status.get("status"), "done")


class _FakeManager:
    def __init__(self, status: dict[str, object]) -> None:
        self._status = status
        self.stopped = False
        self.joined = False

    def status(self) -> dict[str, object]:
        return dict(self._status)

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True


class ServerQuietHelpersTests(unittest.TestCase):
    def test_quiet_run_does_not_block_user_twse_fetches(self) -> None:
        quiet = {"running": True, "status": "running", "mode": "quiet"}
        manual = {"running": True, "status": "running", "mode": "manual"}
        self.assertFalse(_bulk_blocks_twse_fetch("/api/sync", quiet))
        self.assertTrue(_bulk_blocks_twse_fetch("/api/sync", manual))
        self.assertFalse(_bulk_blocks_twse_fetch("/api/not-blocked", manual))

    def test_preempt_stops_only_quiet_runs(self) -> None:
        quiet = _FakeManager({"running": True, "mode": "quiet"})
        _preempt_quiet_run(quiet)
        self.assertTrue(quiet.stopped)
        self.assertTrue(quiet.joined)

        manual = _FakeManager({"running": True, "mode": "manual"})
        _preempt_quiet_run(manual)
        self.assertFalse(manual.stopped)

        idle = _FakeManager({"running": False, "mode": "quiet"})
        _preempt_quiet_run(idle)
        self.assertFalse(idle.stopped)

    def test_quiet_sync_due_respects_min_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                self.assertTrue(_quiet_sync_due(store))
                store.set_json_cache(QUIET_SYNC_STATE_KEY, {"last": "now"})
                self.assertFalse(_quiet_sync_due(store))
                later = datetime.now() + timedelta(hours=5)
                self.assertTrue(_quiet_sync_due(store, now=later))

    def test_quiet_request_interval_is_slower_than_manual_default(self) -> None:
        self.assertGreater(QUIET_REQUEST_INTERVAL, 0.2)


if __name__ == "__main__":
    unittest.main()
