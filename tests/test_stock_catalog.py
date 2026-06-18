from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.catalog.stocks import search_stock_catalog


class StockCatalogTests(unittest.TestCase):
    def test_search_stock_catalog_matches_code_and_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stock_catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2303", "market": "TWSE", "name": "聯電", "short_name": "聯電"},
                            {"stock_id": "2330", "market": "TWSE", "name": "台積電", "short_name": "台積電"},
                            {"stock_id": "2344", "market": "TWSE", "name": "華邦電", "short_name": "華邦電"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            by_name = search_stock_catalog("台積", path=path)
            by_code = search_stock_catalog("230", path=path)

        self.assertEqual(by_name[0].stock_id, "2330")
        self.assertEqual(by_code[0].stock_id, "2303")


if __name__ == "__main__":
    unittest.main()
