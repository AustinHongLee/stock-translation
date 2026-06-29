from __future__ import annotations

import unittest

from app.update.checker import check_for_update, is_newer, parse_version, select_release_asset


def release(tag: str, *, assets: list[dict[str, object]] | None = None, body: str = "") -> dict[str, object]:
    return {
        "tag_name": tag,
        "html_url": f"https://github.example/releases/tag/{tag}",
        "body": body,
        "assets": assets if assets is not None else [zip_asset("StockTranslator-v2.1.0.zip")],
    }


def zip_asset(name: str, *, size: int = 1234) -> dict[str, object]:
    return {
        "name": name,
        "browser_download_url": f"https://download.example/{name}",
        "size": size,
    }


class UpdateCheckerTests(unittest.TestCase):
    def test_parse_version_accepts_plain_and_v_prefixed_semver(self) -> None:
        self.assertEqual(parse_version("2.1.0"), (2, 1, 0))
        self.assertEqual(parse_version("v2.1.0"), (2, 1, 0))
        self.assertIsNone(parse_version("v2.1"))
        self.assertIsNone(parse_version("latest"))

    def test_is_newer_handles_new_same_old_and_bad_versions(self) -> None:
        self.assertTrue(is_newer("v2.1.0", "2.0.0"))
        self.assertFalse(is_newer("v2.0.0", "2.0.0"))
        self.assertFalse(is_newer("v1.9.9", "2.0.0"))
        self.assertFalse(is_newer("bad", "2.0.0"))
        self.assertFalse(is_newer("v2.1.0", "bad"))

    def test_check_for_update_reports_new_release_with_zip_asset(self) -> None:
        payload = check_for_update(
            "2.0.0",
            lambda: release(
                "v2.1.0",
                assets=[
                    zip_asset("notes.txt"),
                    zip_asset("StockTranslator-v2.1.0.zip", size=5678),
                    zip_asset("StockTranslator-v2.1.0.zip.sha256"),
                ],
                body="sha256: " + "a" * 64,
            ),
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["latest"], "v2.1.0")
        self.assertEqual(payload["url"], "https://download.example/StockTranslator-v2.1.0.zip")
        self.assertEqual(payload["manual_url"], payload["url"])
        self.assertEqual(payload["size"], 5678)
        self.assertEqual(payload["sha256"], "a" * 64)
        self.assertEqual(payload["sha256_url"], "https://download.example/StockTranslator-v2.1.0.zip.sha256")

    def test_check_for_update_returns_false_for_same_or_older_release(self) -> None:
        same = check_for_update("2.0.0", lambda: release("v2.0.0"))
        older = check_for_update("2.0.0", lambda: release("v1.9.9"))

        self.assertFalse(same["available"])
        self.assertFalse(older["available"])
        self.assertEqual(same["message"], "目前已是最新版本。")

    def test_check_for_update_handles_bad_tag_missing_asset_and_network_failure(self) -> None:
        bad_tag = check_for_update("2.0.0", lambda: release("nightly"))
        missing_asset = check_for_update("2.0.0", lambda: release("v2.1.0", assets=[]))
        failed = check_for_update("2.0.0", lambda: (_ for _ in ()).throw(OSError("offline")))

        self.assertFalse(bad_tag["available"])
        self.assertFalse(missing_asset["available"])
        self.assertIn("沒有可下載", missing_asset["message"])
        self.assertFalse(failed["available"])
        self.assertEqual(failed["latest"], "2.0.0")

    def test_select_release_asset_prefers_named_zip(self) -> None:
        selected = select_release_asset(
            [
                zip_asset("random.zip"),
                zip_asset("StockTranslator-v2.1.0.zip"),
            ]
        )

        self.assertEqual(selected["name"], "StockTranslator-v2.1.0.zip")


if __name__ == "__main__":
    unittest.main()
