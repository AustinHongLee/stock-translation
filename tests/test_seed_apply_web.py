from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app.store.seed_merge import file_sha256
from app.store.sqlite_store import SQLiteStore
from app.web import server as web_server
from app.web.server import StockTranslatorServer


class SeedApplyWebTests(unittest.TestCase):
    def test_manual_seed_apply_endpoint_merges_seed_and_refreshes_app_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_root = root / "localappdata" / "StockTranslator" / "data"
            db_path = data_root / "stock_translator.sqlite3"
            seed_dir = root / "seed"
            seed_db = seed_dir / "seed.sqlite3"
            data_root.mkdir(parents=True)
            seed_dir.mkdir()
            with SQLiteStore(db_path) as store:
                _insert_daily(store.conn, "2330", "2026-06-30", 100.0)
                store.conn.execute("INSERT INTO watchlist (stock_id, added_at) VALUES (?, ?)", ("2330", "2026-07-01"))
                store.conn.commit()
            with SQLiteStore(seed_db) as store:
                _insert_daily(store.conn, "2330", "2026-06-30", 999.0)
                _insert_daily(store.conn, "2317", "2026-06-30", 50.0)
                store.conn.commit()
            (seed_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "data_snapshot_version": 20260703,
                        "generated_at": "2026-07-03T00:00:00Z",
                        "app_min_version": "2.0.0",
                        "sha256": file_sha256(seed_db),
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch("app.web.server.seed_dir", return_value=seed_dir),
                patch("app.web.server.data_dir", return_value=data_root),
                patch.object(web_server, "APP_VERSION", "2.0.6"),
            ):
                httpd = StockTranslatorServer(("127.0.0.1", 0), db_path)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base_url = f"http://127.0.0.1:{httpd.server_port}"
                try:
                    before = _request_json(f"{base_url}/api/app-info")
                    applied = _request_json(f"{base_url}/api/data/seed/apply", method="POST")
                    after = _request_json(f"{base_url}/api/app-info")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=2)

            with SQLiteStore(db_path) as store:
                rows = store.conn.execute(
                    "SELECT stock_id, close FROM daily_prices ORDER BY stock_id"
                ).fetchall()
                watchlist = store.conn.execute("SELECT stock_id FROM watchlist ORDER BY stock_id").fetchall()

        self.assertEqual(before["data_snapshot_version"], 0)
        self.assertTrue(applied["ok"])
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["version"], 20260703)
        self.assertEqual(applied["app_info"]["data_snapshot_version"], 20260703)  # type: ignore[index]
        self.assertEqual(after["data_snapshot_version"], 20260703)
        self.assertEqual([(row["stock_id"], row["close"]) for row in rows], [("2317", 50.0), ("2330", 100.0)])
        self.assertEqual([row["stock_id"] for row in watchlist], ["2330"])

    def test_data_hub_check_and_apply_endpoints_are_best_effort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "data" / "stock_translator.sqlite3"
            db_path.parent.mkdir(parents=True)
            with SQLiteStore(db_path):
                pass

            web_server._DATA_HUB_CHECK_CACHE.update({"checked_at": 0.0, "payload": None, "current_version": 0})
            with (
                patch(
                    "app.web.server.check_for_data_hub",
                    return_value={
                        "available": True,
                        "current_version": 0,
                        "version": 20260708,
                        "url": "https://download.example/StockTranslator-official-data-20260708.zip",
                        "message": "找到較新的官方資料樞紐。",
                    },
                ),
                patch(
                    "app.web.server._apply_data_hub_now",
                    return_value={
                        "applied": True,
                        "version": 20260708,
                        "rows": 5,
                    },
                ),
            ):
                httpd = StockTranslatorServer(("127.0.0.1", 0), db_path)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base_url = f"http://127.0.0.1:{httpd.server_port}"
                try:
                    checked = _request_json(f"{base_url}/api/data/hub/check?force=1")
                    applied = _request_json(f"{base_url}/api/data/hub/apply", method="POST")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=2)

        self.assertTrue(checked["available"])
        self.assertEqual(checked["version"], 20260708)
        self.assertTrue(applied["ok"])
        self.assertIn("官方資料樞紐已套用", str(applied["message"]))


def _request_json(url: str, *, method: str = "GET") -> dict[str, object]:
    data = b"{}" if method != "GET" else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _insert_daily(conn: sqlite3.Connection, stock_id: str, day: str, close: float) -> None:
    conn.execute(
        """
        INSERT INTO daily_prices (
            stock_id, date, open, high, low, close, volume,
            trade_value, transaction_count, change, note, source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (stock_id, day, close, close, close, close, 1000, 10000, 10, 0.0, "", "test", "2026-07-03T00:00:00"),
    )


if __name__ == "__main__":
    unittest.main()
