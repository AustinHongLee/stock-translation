from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.models import DailyPrice, StockProfile
from app.store.sqlite_store import SQLiteStore
from tools.backfill_tpex_history import backfill_tpex_history


class FakeTpexClient:
    def __init__(self) -> None:
        self.calls: list[tuple[date, set[str]]] = []

    def fetch_all_daily_prices_for_date(
        self, day: date, *, stock_ids: set[str]
    ) -> list[DailyPrice]:
        self.calls.append((day, set(stock_ids)))
        return [
            DailyPrice(
                stock_id="3105",
                date=day,
                open=10,
                high=11,
                low=9,
                close=10.5,
                volume=1000,
                source="TPEX_DAILY_QUOTES",
            )
        ]


class BackfillTpexHistoryTests(unittest.TestCase):
    def _make_db(self, root: Path, latest_day: date) -> Path:
        db_path = root / "hub.sqlite3"
        with SQLiteStore(db_path) as store:
            store.upsert_profiles(
                [
                    StockProfile("3105", "穩懋", "穩懋", market="TPEX"),
                    StockProfile("2330", "台積電", "台積電", market="TWSE"),
                ]
            )
            store.upsert_daily_prices(
                [
                    DailyPrice(
                        stock_id="2330",
                        date=latest_day,
                        open=100,
                        high=101,
                        low=99,
                        close=100,
                        volume=1000,
                    )
                ]
            )
        return db_path

    def test_backfill_filters_to_tpex_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._make_db(Path(tmp), date(2026, 8, 24))
            client = FakeTpexClient()

            first = backfill_tpex_history(
                db_path,
                history_days=1,
                max_days=5,
                request_interval=0,
                client=client,
            )
            second = backfill_tpex_history(
                db_path,
                history_days=1,
                max_days=5,
                request_interval=0,
                client=client,
            )

            self.assertTrue(first["publish"])
            self.assertEqual(first["rows"], 1)
            self.assertFalse(second["publish"])
            self.assertEqual(client.calls, [(date(2026, 8, 24), {"3105"})])
            with SQLiteStore(db_path) as store:
                self.assertEqual(store.count_daily_prices("3105"), 1)

    def test_backfill_processes_newest_days_first_and_honors_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._make_db(Path(tmp), date(2026, 8, 24))
            client = FakeTpexClient()

            result = backfill_tpex_history(
                db_path,
                history_days=10,
                max_days=2,
                request_interval=0,
                client=client,
            )

            self.assertEqual(result["processed_days"], 2)
            self.assertEqual(
                [item[0] for item in client.calls],
                [date(2026, 8, 24), date(2026, 8, 21)],
            )
            self.assertGreater(result["remaining_days"], 0)


if __name__ == "__main__":
    unittest.main()
