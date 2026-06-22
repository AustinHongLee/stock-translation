from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path


STATIC_DIR = Path("app/ui/static")


class PWAAssetsTests(unittest.TestCase):
    def test_manifest_has_installable_basics_and_icons(self) -> None:
        manifest = json.loads((STATIC_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))

        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["theme_color"], "#1C3D5A")

        icons = {item["sizes"]: item for item in manifest["icons"]}
        self.assertIn("192x192", icons)
        self.assertIn("512x512", icons)
        for size in (192, 512):
            icon_path = STATIC_DIR / icons[f"{size}x{size}"]["src"].removeprefix("/static/")
            self.assertTrue(icon_path.is_file())
            self.assertEqual(_png_size(icon_path), (size, size))

    def test_service_worker_caches_shell_but_not_api(self) -> None:
        sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")

        self.assertIn("CACHE_NAME", sw)
        self.assertIn("stock-translator-shell-v2", sw)
        self.assertIn("/static/app.css", sw)
        self.assertIn("/static/app.js", sw)
        self.assertIn('url.pathname.startsWith("/api/")', sw)
        self.assertIn("networkFirst(request)", sw)
        self.assertIn("reloadControlledClients", sw)
        self.assertIn("client.navigate(client.url)", sw)

    def test_index_links_manifest_icon_and_service_worker_registration(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('rel="manifest"', html)
        self.assertIn('name="theme-color"', html)
        self.assertIn("app-icon-192.png", html)
        self.assertIn('serviceWorker.register("/sw.js")', js)


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    if not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", header[16:24])
    return width, height
