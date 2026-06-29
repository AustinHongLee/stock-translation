from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def test_frozen_data_dir_uses_localappdata_stocktranslator_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_app_data = root / "LocalAppData"
            exe_path = root / "install" / "StockTranslator.exe"
            exe_path.parent.mkdir(parents=True)

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(exe_path)),
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                self.assertEqual(runtime_paths.external_data_root(), local_app_data / "StockTranslator")
                self.assertEqual(runtime_paths.data_dir(), local_app_data / "StockTranslator" / "data")

    def test_migrate_legacy_data_copies_database_and_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_app_data = root / "LocalAppData"
            exe_path = root / "install" / "StockTranslator.exe"
            legacy_data = exe_path.parent / "data"
            legacy_data.mkdir(parents=True)
            (legacy_data / "stock_translator.sqlite3").write_bytes(b"legacy-db")
            (legacy_data / "stock_translator.sqlite3-wal").write_bytes(b"legacy-wal")
            (legacy_data / "stock_translator.sqlite3-shm").write_bytes(b"legacy-shm")
            (legacy_data / "value_screener.json").write_text("{}", encoding="utf-8")

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(exe_path)),
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                self.assertTrue(runtime_paths.migrate_legacy_data())
                new_data = local_app_data / "StockTranslator" / "data"

            self.assertEqual((new_data / "stock_translator.sqlite3").read_bytes(), b"legacy-db")
            self.assertEqual((new_data / "stock_translator.sqlite3-wal").read_bytes(), b"legacy-wal")
            self.assertEqual((new_data / "stock_translator.sqlite3-shm").read_bytes(), b"legacy-shm")
            self.assertEqual((new_data / "value_screener.json").read_text(encoding="utf-8"), "{}")
            self.assertTrue((legacy_data / "stock_translator.sqlite3").is_file())

    def test_migrate_legacy_data_does_not_overwrite_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_app_data = root / "LocalAppData"
            exe_path = root / "install" / "StockTranslator.exe"
            legacy_data = exe_path.parent / "data"
            legacy_data.mkdir(parents=True)
            (legacy_data / "stock_translator.sqlite3").write_bytes(b"legacy-db")
            new_data = local_app_data / "StockTranslator" / "data"
            new_data.mkdir(parents=True)
            (new_data / "stock_translator.sqlite3").write_bytes(b"existing-db")

            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(exe_path)),
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                self.assertFalse(runtime_paths.migrate_legacy_data())

            self.assertEqual((new_data / "stock_translator.sqlite3").read_bytes(), b"existing-db")

    def test_development_mode_data_dir_stays_repo_root_data(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(runtime_paths.external_data_root(), runtime_paths.resource_root())
            self.assertEqual(runtime_paths.data_dir(), runtime_paths.resource_root() / "data")


if __name__ == "__main__":
    unittest.main()
