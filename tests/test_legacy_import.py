from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.store.legacy_import import (
    copy_legacy_snapshot,
    count_daily_stocks,
    import_legacy_data,
    legacy_import_status,
)


def _make_current(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE daily_prices (
            stock_id TEXT, date TEXT, close REAL, note TEXT,
            PRIMARY KEY (stock_id, date)
        );
        CREATE TABLE watchlist (stock_id TEXT PRIMARY KEY);
        CREATE TABLE app_cache (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    conn.commit()
    conn.close()


def _make_legacy(path: Path, *, stocks: int = 3, with_note: bool = False) -> None:
    conn = sqlite3.connect(str(path))
    cols = "stock_id TEXT, date TEXT, close REAL" + (", note TEXT" if with_note else "")
    conn.executescript(
        f"""
        CREATE TABLE daily_prices ({cols}, PRIMARY KEY (stock_id, date));
        CREATE TABLE watchlist (stock_id TEXT PRIMARY KEY);
        CREATE TABLE app_cache (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    for i in range(stocks):
        sid = f"{1000 + i}"
        conn.execute("INSERT INTO daily_prices (stock_id, date, close) VALUES (?,?,?)", (sid, "2026-06-26", 10.0 + i))
        conn.execute("INSERT INTO watchlist (stock_id) VALUES (?)", (sid,))
    conn.execute("INSERT INTO app_cache (key, value) VALUES ('legacy_only','x')")
    conn.commit()
    conn.close()


class LegacyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.current = self.tmp / "current" / "stock_translator.sqlite3"
        self.current.parent.mkdir(parents=True)
        self.legacy_dir = self.tmp / "legacy"
        self.legacy_dir.mkdir()
        self.legacy = self.legacy_dir / "stock_translator.sqlite3"

    def test_count_missing_file_is_zero(self) -> None:
        self.assertEqual(count_daily_stocks(self.tmp / "nope.sqlite3"), 0)

    def test_status_available_when_legacy_has_more(self) -> None:
        _make_current(self.current)
        _make_legacy(self.legacy, stocks=3)
        status = legacy_import_status(self.legacy, self.current)
        self.assertTrue(status["available"])
        self.assertEqual(status["legacy_stock_count"], 3)
        self.assertEqual(status["current_stock_count"], 0)

    def test_status_not_available_when_current_has_equal_or_more(self) -> None:
        _make_current(self.current)
        _make_legacy(self.legacy, stocks=0)
        self.assertFalse(legacy_import_status(self.legacy, self.current)["available"])

    def test_status_not_available_without_legacy(self) -> None:
        _make_current(self.current)
        self.assertFalse(legacy_import_status(self.legacy, self.current)["available"])

    def test_import_merges_and_is_idempotent_and_skips_cache(self) -> None:
        _make_current(self.current)
        _make_legacy(self.legacy, stocks=3)
        first = import_legacy_data(self.legacy, self.current)
        self.assertEqual(first["imported"].get("daily_prices"), 3)
        self.assertEqual(first["imported"].get("watchlist"), 3)
        self.assertEqual(count_daily_stocks(self.current), 3)
        # app_cache 不在白名單，不應被匯入
        conn = sqlite3.connect(str(self.current))
        n_cache = conn.execute("SELECT COUNT(*) FROM app_cache").fetchone()[0]
        conn.close()
        self.assertEqual(n_cache, 0)
        # 再跑一次：INSERT OR IGNORE → 不再新增（冪等）
        second = import_legacy_data(self.legacy, self.current)
        self.assertEqual(second["rows"], 0)

    def test_import_handles_column_drift(self) -> None:
        # 現用表有 note 欄，舊表沒有 → 只匯入共同欄位，不報錯
        _make_current(self.current)
        _make_legacy(self.legacy, stocks=2, with_note=False)
        summary = import_legacy_data(self.legacy, self.current)
        self.assertEqual(summary["imported"].get("daily_prices"), 2)
        conn = sqlite3.connect(str(self.current))
        row = conn.execute("SELECT close, note FROM daily_prices WHERE stock_id='1000'").fetchone()
        conn.close()
        self.assertEqual(row[0], 10.0)
        self.assertIsNone(row[1])

    def test_copy_snapshot(self) -> None:
        (self.legacy_dir / "value_screener.json").write_text("{}", encoding="utf-8")
        ok = copy_legacy_snapshot(self.legacy_dir, self.current.parent)
        self.assertTrue(ok)
        self.assertTrue((self.current.parent / "value_screener.json").is_file())


if __name__ == "__main__":
    unittest.main()
