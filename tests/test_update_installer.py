from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.update.installer import fetch_remote_sha256, find_payload_dir, safe_extract_zip, write_updater_bat


class UpdateInstallerTests(unittest.TestCase):
    def test_safe_extract_rejects_zip_slip_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "bad")

            with self.assertRaises(ValueError):
                safe_extract_zip(archive, root / "out")

    def test_find_payload_dir_accepts_exe_and_internal_under_nested_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "release" / "股票翻譯機"
            (payload / "_internal").mkdir(parents=True)
            (payload / "股票翻譯機.exe").write_bytes(b"exe")

            self.assertEqual(find_payload_dir(root), payload)

    def test_updater_batch_excludes_data_and_mentions_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "payload"
            install = root / "install"
            output = root / "out"
            payload.mkdir()
            install.mkdir()
            exe = install / "股票翻譯機.exe"
            exe.write_bytes(b"old")

            updater = write_updater_bat(
                payload_dir=payload,
                install_dir=install,
                executable=exe,
                pid=1234,
                output_dir=output,
            )
            text = updater.read_text(encoding="utf-8")

        self.assertIn("/XD data", text)
        self.assertIn("rollback", text)
        self.assertIn("_internal", text)
        self.assertIn("Data folder was not touched", text)

    def test_fetch_remote_sha256_parses_checksum_text(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return (("b" * 64) + "  StockTranslator-v2.1.0.zip\n").encode("utf-8")

        with patch("app.update.installer.urllib.request.urlopen", return_value=FakeResponse()):
            self.assertEqual(
                fetch_remote_sha256("https://download.example/check.sha256", asset_name="StockTranslator-v2.1.0.zip"),
                "b" * 64,
            )


if __name__ == "__main__":
    unittest.main()
