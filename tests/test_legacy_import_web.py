from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from app.web import server as web_server
from app.web.server import StockTranslatorServer


class LegacyImportWebTests(unittest.TestCase):
    def test_legacy_import_get_shape_and_dismiss_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_root = root / "localappdata" / "StockTranslator" / "data"
            install_root = root / "install"
            db_path = data_root / "stock_translator.sqlite3"
            data_root.mkdir(parents=True)
            install_root.mkdir()

            with (
                patch.object(web_server.sys, "frozen", True, create=True),
                patch("app.web.server.data_dir", return_value=data_root),
                patch("app.web.server.external_root", return_value=install_root),
                patch(
                    "app.web.server.legacy_import_status",
                    return_value={
                        "available": True,
                        "legacy_stock_count": 42,
                        "current_stock_count": 0,
                    },
                ),
            ):
                httpd = StockTranslatorServer(("127.0.0.1", 0), db_path)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base_url = f"http://127.0.0.1:{httpd.server_port}"
                try:
                    first = _request_json(f"{base_url}/api/data/legacy-import")
                    dismissed = _request_json(f"{base_url}/api/data/legacy-import/dismiss", method="POST")
                    second = _request_json(f"{base_url}/api/data/legacy-import")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=2)

        self.assertTrue(first["available"])
        self.assertFalse(first["dismissed"])
        self.assertEqual(first["legacy_stock_count"], 42)
        self.assertEqual(first["current_stock_count"], 0)
        self.assertTrue(dismissed["ok"])
        self.assertFalse(second["available"])
        self.assertTrue(second["dismissed"])


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


if __name__ == "__main__":
    unittest.main()
