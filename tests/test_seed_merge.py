from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.store.seed_merge import (
    SEED_APPLIED_CACHE_KEY,
    applied_seed_version,
    file_sha256,
    maybe_merge_seed,
    read_seed_manifest,
)
from app.store.sqlite_store import SQLiteStore


class SeedMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.current = self.tmp / "current" / "stock_translator.sqlite3"
        self.seed_dir = self.tmp / "seed"
        self.seed_db = self.seed_dir / "seed.sqlite3"
        self.backups = self.tmp / "backups"
        self.seed_dir.mkdir()
        with SQLiteStore(self.current) as store:
            _insert_daily(store.conn, "2330", "2026-06-30", 100.0)
            store.conn.execute("INSERT INTO watchlist (stock_id, added_at) VALUES (?, ?)", ("2330", "2026-07-01"))
            store.set_json_cache("local_data_v2", {"stale": True})
            store.conn.commit()

    def test_merge_adds_missing_market_rows_without_overwriting_existing_or_private_tables(self) -> None:
        self._write_seed(version=20260701)
        with SQLiteStore(self.current) as store:
            result = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
            self.assertTrue(result["applied"])
            self.assertEqual(result["imported"].get("daily_prices"), 1)
            rows = store.conn.execute(
                "SELECT stock_id, close FROM daily_prices ORDER BY stock_id"
            ).fetchall()
            watchlist = store.conn.execute("SELECT stock_id FROM watchlist ORDER BY stock_id").fetchall()
            self.assertIsNone(store.get_json_cache("local_data_v2"))
            self.assertEqual(applied_seed_version(store), 20260701)

        self.assertEqual([(row["stock_id"], row["close"]) for row in rows], [("2317", 50.0), ("2330", 100.0)])
        self.assertEqual([row["stock_id"] for row in watchlist], ["2330"])
        self.assertTrue(any(self.backups.glob("stock_translator.20260701.sqlite3")))

    def test_same_seed_version_is_only_applied_once(self) -> None:
        self._write_seed(version=20260701)
        with SQLiteStore(self.current) as store:
            first = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
            second = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )

        self.assertTrue(first["applied"])
        self.assertFalse(second["applied"])
        self.assertEqual(second["reason"], "already_applied")

    def test_force_merge_reapplies_same_seed_version_for_missing_rows(self) -> None:
        self._write_seed(version=20260701)
        with SQLiteStore(self.current) as store:
            first = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
            self.assertTrue(first["applied"])
            store.conn.execute("DELETE FROM daily_prices WHERE stock_id = ?", ("2317",))
            store.conn.commit()
            forced = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
                force=True,
            )
            rows = store.conn.execute("SELECT stock_id FROM daily_prices WHERE stock_id = '2317'").fetchall()

        self.assertTrue(forced["applied"])
        self.assertEqual(forced["imported"].get("daily_prices"), 1)
        self.assertEqual(len(rows), 1)

    def test_seed_with_bad_hash_or_too_new_app_is_skipped(self) -> None:
        self._write_seed(version=20260701, sha256="0" * 64)
        with SQLiteStore(self.current) as store:
            bad_hash = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
        self.assertFalse(bad_hash["applied"])
        self.assertEqual(bad_hash["reason"], "sha256_mismatch")

        self._write_seed(version=20260702, app_min_version="9.9.9")
        with SQLiteStore(self.current) as store:
            too_new = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
        self.assertFalse(too_new["applied"])
        self.assertEqual(too_new["reason"], "app_too_old")

    def test_missing_or_invalid_manifest_is_noop(self) -> None:
        self.assertIsNone(read_seed_manifest(self.seed_dir))
        with SQLiteStore(self.current) as store:
            result = maybe_merge_seed(
                store,
                seed_dir=self.seed_dir,
                current_db=self.current,
                app_version="2.0.2",
                backups_dir=self.backups,
            )
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "missing_manifest")

    def test_old_backups_are_pruned_to_three(self) -> None:
        with SQLiteStore(self.current) as store:
            for version in range(20260701, 20260706):
                self._write_seed(version=version)
                result = maybe_merge_seed(
                    store,
                    seed_dir=self.seed_dir,
                    current_db=self.current,
                    app_version="2.0.2",
                    backups_dir=self.backups,
                )
                self.assertTrue(result["applied"])
        self.assertLessEqual(len(list(self.backups.glob("stock_translator.*.sqlite3"))), 3)

    def _write_seed(
        self,
        *,
        version: int,
        sha256: str | None = None,
        app_min_version: str = "2.0.0",
    ) -> None:
        if self.seed_db.exists():
            self.seed_db.unlink()
        with SQLiteStore(self.seed_db) as store:
            _insert_daily(store.conn, "2330", "2026-06-30", 999.0)
            _insert_daily(store.conn, "2317", "2026-06-30", 50.0)
            store.conn.execute("INSERT INTO watchlist (stock_id, added_at) VALUES (?, ?)", ("9999", "2026-07-01"))
            store.conn.commit()
        digest = sha256 or file_sha256(self.seed_db)
        (self.seed_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "data_snapshot_version": version,
                    "generated_at": "2026-07-01T00:00:00Z",
                    "app_min_version": app_min_version,
                    "sha256": digest,
                    "tables": {"daily_prices": {"rows": 2}},
                }
            ),
            encoding="utf-8",
        )


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
