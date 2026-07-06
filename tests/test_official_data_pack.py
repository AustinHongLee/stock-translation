from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.store.sqlite_store import SQLiteStore
from tools.build_official_data_pack import build_pack


class OfficialDataPackTests(unittest.TestCase):
    def test_build_pack_keeps_public_data_and_clears_private_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source" / "stock_translator.sqlite3"
            source.parent.mkdir()
            (source.parent / "stock_catalog.json").write_text('{"stocks":[]}', encoding="utf-8")
            (source.parent / "value_screener.json").write_text('{"items":[]}', encoding="utf-8")

            with SQLiteStore(source) as store:
                _insert_daily(store.conn, "2330", "2026-06-30", 100.0)
                store.conn.execute("INSERT INTO watchlist (stock_id, added_at) VALUES (?, ?)", ("2330", "2026-07-01"))
                store.set_json_cache("local_data_v3", {"private": True})
                store.conn.commit()

            manifest = build_pack(source, root / "official_data")

            packed_db = root / "official_data" / "data" / "stock_translator.sqlite3"
            self.assertTrue(packed_db.is_file())
            self.assertTrue((root / "official_data" / "data" / "stock_catalog.json").is_file())
            self.assertTrue((root / "official_data" / "data" / "value_screener.json").is_file())
            self.assertEqual(manifest["tables"]["daily_prices"]["rows"], 1)
            self.assertIn("data/stock_translator.sqlite3", manifest["files"])

            conn = sqlite3.connect(packed_db)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_cache").fetchone()[0], 0)
            finally:
                conn.close()

            written_manifest = json.loads((root / "official_data" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(written_manifest["files"].keys(), manifest["files"].keys())


def _insert_daily(conn: sqlite3.Connection, stock_id: str, day: str, close: float) -> None:
    conn.execute(
        """
        INSERT INTO daily_prices (
            stock_id, date, open, high, low, close, volume,
            trade_value, transaction_count, change, note, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (stock_id, day, close, close, close, close, 1000, 10000, 10, 0.0, "", "test", "2026-07-01T00:00:00"),
    )


if __name__ == "__main__":
    unittest.main()
