from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.models import DailyPrice, StockProfile
from app.store.sqlite_store import SQLiteStore
from tools.prepare_release_data import validate_release_data


class PrepareReleaseDataTests(unittest.TestCase):
    def _make_hub(self, root: Path, *, deep: bool) -> Path:
        hub = root / "official_data"
        db_path = hub / "data" / "stock_translator.sqlite3"
        db_path.parent.mkdir(parents=True)
        today = date(2026, 8, 25)
        with SQLiteStore(db_path) as store:
            store.upsert_profiles(
                [
                    StockProfile("3105", "穩懋", "穩懋", market="TPEX"),
                    StockProfile("5347", "世界", "世界", market="TPEX"),
                ]
            )
            rows = []
            for stock_id in ("3105", "5347"):
                days = (today, today - timedelta(days=1)) if deep else (today,)
                for day in days:
                    rows.append(
                        DailyPrice(
                            stock_id=stock_id,
                            date=day,
                            open=10,
                            high=11,
                            low=9,
                            close=10,
                            volume=1000,
                        )
                    )
            store.upsert_daily_prices(rows)
        (hub / "manifest.json").write_text(
            json.dumps({"data_snapshot_version": 20260825}), encoding="utf-8"
        )
        return hub

    def test_validate_accepts_fresh_deep_tpex_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stats = validate_release_data(
                self._make_hub(Path(tmp), deep=True),
                max_stale_days=2,
                min_tpex_deep_stocks=2,
                min_tpex_rows=2,
                today=date(2026, 8, 25),
            )
        self.assertEqual(stats["deep_tpex_stocks"], 2)

    def test_validate_rejects_shallow_tpex_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "baseline 不完整"):
                validate_release_data(
                    self._make_hub(Path(tmp), deep=False),
                    max_stale_days=2,
                    min_tpex_deep_stocks=2,
                    min_tpex_rows=2,
                    today=date(2026, 8, 25),
                )


if __name__ == "__main__":
    unittest.main()
