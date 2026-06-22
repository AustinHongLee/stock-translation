from __future__ import annotations

import unittest
from pathlib import Path


STATIC_DIR = Path("app/ui/static")


class UIThemeTests(unittest.TestCase):
    def test_index_exposes_theme_toggle_and_early_theme_bootstrap(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="themeToggle"', html)
        self.assertIn('aria-pressed="false"', html)
        self.assertIn("stockTranslator.theme", html)
        self.assertIn("document.documentElement.dataset.theme", html)

    def test_css_declares_dark_theme_variables(self) -> None:
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn(':root[data-theme="dark"]', css)
        self.assertIn("--chart-bg:", css)
        self.assertIn("--on-brand:", css)
        self.assertIn(".theme-toggle.is-dark .theme-icon-sun", css)

    def test_js_persists_theme_and_repaints_canvases(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("const THEME_STORAGE_KEY", js)
        self.assertIn("function applyTheme", js)
        self.assertIn("function toggleTheme", js)
        self.assertIn("window.localStorage?.setItem(THEME_STORAGE_KEY", js)
        self.assertIn("function chartThemeColors", js)
        self.assertIn("refreshThemeCanvases", js)


if __name__ == "__main__":
    unittest.main()
