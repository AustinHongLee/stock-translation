from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.update.data_hub import (
    check_for_data_hub,
    find_data_hub_dir,
    parse_data_hub_version,
    prepare_data_hub,
    select_data_hub_asset,
)
from tools.package_data_hub import package_data_hub


def asset(name: str, *, size: int = 1234) -> dict[str, object]:
    return {
        "name": name,
        "browser_download_url": f"https://download.example/{name}",
        "size": size,
    }


def release(*, assets: list[dict[str, object]], body: str = "") -> dict[str, object]:
    return {
        "html_url": "https://github.example/releases/latest",
        "body": body,
        "assets": assets,
    }


class DataHubTests(unittest.TestCase):
    def test_select_data_hub_asset_prefers_newest_official_data_zip(self) -> None:
        selected = select_data_hub_asset(
            [
                asset("StockTranslator-v2.0.10.zip"),
                asset("StockTranslator-official-data-20260706.zip"),
                asset("StockTranslator-official-data-20260708.zip"),
            ]
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "StockTranslator-official-data-20260708.zip")  # type: ignore[index]
        self.assertEqual(parse_data_hub_version("StockTranslator-official-data-20260708.zip"), 20260708)

    def test_check_for_data_hub_reports_newer_asset_and_sha256_url(self) -> None:
        payload = check_for_data_hub(
            20260706,
            lambda: release(
                assets=[
                    asset("StockTranslator-official-data-20260708.zip"),
                    asset("StockTranslator-official-data-20260708.zip.sha256"),
                ],
            ),
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["version"], 20260708)
        self.assertEqual(payload["url"], "https://download.example/StockTranslator-official-data-20260708.zip")
        self.assertEqual(payload["sha256_url"], "https://download.example/StockTranslator-official-data-20260708.zip.sha256")

    def test_check_for_data_hub_skips_same_or_missing_asset(self) -> None:
        same = check_for_data_hub(20260708, lambda: release(assets=[asset("StockTranslator-official-data-20260708.zip")]))
        missing = check_for_data_hub(20260701, lambda: release(assets=[asset("StockTranslator-v2.0.10.zip")]))

        self.assertFalse(same["available"])
        self.assertFalse(missing["available"])

    def test_package_data_hub_and_prepare_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            official = root / "official_data"
            data_dir = official / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "stock_translator.sqlite3").write_bytes(b"sqlite")
            (official / "manifest.json").write_text(
                json.dumps(
                    {
                        "data_snapshot_version": 20260708,
                        "files": {
                            "data/stock_translator.sqlite3": {
                                "sha256": "x",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            zip_path, sha_path, digest = package_data_hub(official, root / "dist")
            self.assertTrue(zip_path.is_file())
            self.assertTrue(sha_path.read_text(encoding="utf-8").startswith(digest))

            work = root / "work"
            downloaded = root / "downloaded.zip"
            downloaded.write_bytes(zip_path.read_bytes())
            with patch("app.update.data_hub.download_file", side_effect=lambda _url, target, **_kw: target.write_bytes(downloaded.read_bytes())):
                prepared = prepare_data_hub(
                    {
                        "version": 20260708,
                        "url": "https://download.example/data.zip",
                        "asset_name": zip_path.name,
                        "sha256": digest,
                    },
                    work_root=work,
                )

            self.assertEqual(prepared.version, 20260708)
            self.assertEqual(find_data_hub_dir(prepared.hub_dir), prepared.hub_dir)
            self.assertTrue((prepared.hub_dir / "manifest.json").is_file())

            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn("data/stock_translator.sqlite3", archive.namelist())


if __name__ == "__main__":
    unittest.main()
