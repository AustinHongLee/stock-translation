from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.models import DailyPrice, InstitutionalTrade, StockProfile
from app.store.sqlite_store import SQLiteStore
from tools.build_official_data_pack import build_pack
from tools import daily_hub_update


class FakeHubClient:
    """daily_hub_update 用的假 TWSE client：全部整批端點、零網路。"""

    def __init__(self, *, request_interval: float = 0.0, latest_day: date | None = None) -> None:
        self.request_interval = request_interval
        self.latest_day = latest_day or date(2026, 7, 13)
        self.t86_calls: list[date] = []

    def fetch_listed_profiles(self) -> list[StockProfile]:
        return [StockProfile(stock_id="2330", name="台積電", short_name="台積電")]

    def fetch_latest_all_prices(self) -> list[DailyPrice]:
        return [
            DailyPrice("2330", self.latest_day, 10, 11, 9, 10, 1000, source="TWSE_STOCK_DAY_ALL"),
            DailyPrice("020039", self.latest_day, 5, 6, 4, 5, 500, source="TWSE_STOCK_DAY_ALL"),
        ]

    def fetch_institutional_trades_for_date(self, day: date) -> list[InstitutionalTrade]:
        self.t86_calls.append(day)
        return [
            InstitutionalTrade(
                stock_id="2330", date=day, foreign_net=1, trust_net=0, dealer_net=0, total_net=1
            )
        ]

    def fetch_all_monthly_revenues(self) -> list[object]:
        return []

    def fetch_all_market_valuations(self) -> list[object]:
        return []

    def fetch_all_financial_statements(self) -> list[object]:
        return []

    def fetch_all_dividend_records(self) -> list[object]:
        return []

    def fetch_all_historical_dividend_records(self, start_date: date, end_date: date) -> list[object]:
        return []


def _run_main(db_path: Path, *extra_args: str) -> str:
    argv = ["daily_hub_update.py", "--db", str(db_path), "--request-interval", "0", *extra_args]
    buffer = io.StringIO()
    with patch("sys.argv", argv), redirect_stdout(buffer):
        code = daily_hub_update.main()
    output = buffer.getvalue()
    assert code == 0, f"unexpected exit code {code}: {output}"
    return output


class DailyHubUpdateTests(unittest.TestCase):
    def _baseline(self, root: Path) -> Path:
        db_path = root / "stock_translator.sqlite3"
        with SQLiteStore(db_path) as store:
            store.upsert_daily_prices(
                [DailyPrice("2330", date(2026, 6, 29), 10, 11, 9, 10, 1000, source="TWSE_STOCK_DAY")]
            )
        return db_path

    def test_applies_daily_increment_and_reports_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._baseline(Path(tmp))
            fake = FakeHubClient()

            with patch.object(daily_hub_update, "TwseClient", return_value=fake):
                output = _run_main(db_path)

            self.assertIn("publish=yes", output)
            with SQLiteStore(db_path) as store:
                latest = store.conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
                self.assertEqual(latest, "2026-07-13")
                t86_rows = store.conn.execute(
                    "SELECT COUNT(*) FROM institutional_trades"
                ).fetchone()[0]
                self.assertGreater(t86_rows, 0)
            # T86 只補近 N 個交易日
            self.assertLessEqual(
                len(fake.t86_calls), daily_hub_update.T86_LOOKBACK_TRADING_DAYS
            )

    def test_second_run_same_day_is_idempotent_no_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._baseline(Path(tmp))
            fake = FakeHubClient()

            with patch.object(daily_hub_update, "TwseClient", return_value=fake):
                first = _run_main(db_path)
                second = _run_main(db_path)

            self.assertIn("publish=yes", first)
            self.assertIn("publish=no", second)
            self.assertIn("未前進", second)

    def test_skip_t86_flag_avoids_rwd_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._baseline(Path(tmp))
            fake = FakeHubClient()

            with patch.object(daily_hub_update, "TwseClient", return_value=fake):
                output = _run_main(db_path, "--skip-t86")

            self.assertIn("publish=yes", output)
            self.assertEqual(fake.t86_calls, [])

    def test_build_pack_app_min_version_override(self) -> None:
        """每日包的版本閘要能傳承 baseline，不被 main 分支的 APP_VERSION 綁架。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = self._baseline(root)

            manifest = build_pack(db_path, root / "pack", app_min_version="2.0.9")
            self.assertEqual(manifest["app_min_version"], "2.0.9")

            from app.version import APP_VERSION

            default_manifest = build_pack(db_path, root / "pack_default")
            self.assertEqual(default_manifest["app_min_version"], APP_VERSION)


class HubPreflightTests(unittest.TestCase):
    def test_non_trading_day_says_no(self) -> None:
        from tools import hub_preflight

        class Sunday:
            @staticmethod
            def date() -> date:
                return date(2026, 7, 12)  # 週日

        with (
            patch.object(hub_preflight, "datetime") as fake_dt,
            patch.dict("os.environ", {"FORCE_RUN": ""}, clear=False),
        ):
            fake_dt.now.return_value = Sunday()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = hub_preflight.main()

        self.assertEqual(code, 0)
        self.assertIn("proceed=no", buffer.getvalue())

    def test_trading_day_with_reachable_endpoints_says_yes(self) -> None:
        from tools import hub_preflight

        class Tuesday:
            @staticmethod
            def date() -> date:
                return date(2026, 7, 14)  # 週二交易日

        with (
            patch.object(hub_preflight, "datetime") as fake_dt,
            patch.object(hub_preflight, "_probe", return_value=(True, "ok")),
            patch.dict("os.environ", {"FORCE_RUN": ""}, clear=False),
        ):
            fake_dt.now.return_value = Tuesday()
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = hub_preflight.main()

        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("proceed=yes", output)
        self.assertIn("t86=yes", output)


if __name__ == "__main__":
    unittest.main()
