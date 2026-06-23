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

    def test_app_js_documents_single_file_sections_and_error_state(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("app.js 分區地圖", js)
        self.assertIn("未導入打包器前先維持單檔", js)
        self.assertIn("function renderLocalDataError", js)
        self.assertIn('stateMessageHTML("error", "讀取失敗"', js)

    def test_stock_page_exposes_html_report_export(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="stockReportButton"', html)
        self.assertIn("匯出研究報告", html)
        self.assertIn("stockReportButton", js)
        self.assertIn("function exportStockReport", js)
        self.assertIn(".html", js)

    def test_stock_page_exposes_fundamental_trend_cards(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn('id="fundamentalTrends"', html)
        self.assertIn("payload.fundamental_trends", js)
        self.assertIn("function renderFundamentalTrends", js)
        self.assertIn("function renderMiniTrendSvg", js)
        self.assertIn(".fundamental-trend-grid", css)

    def test_dashboard_watchlist_board_has_status_tags(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("watchlist-board-row", js)
        self.assertIn("function watchlistBoardTag", js)
        self.assertIn("board.risk", js)
        self.assertIn(".watchlist-board-tags", css)
        self.assertIn(".watchlist-board-tag", css)

    def test_dashboard_compare_view_has_form_and_table(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("compareForm", html)
        self.assertIn("compareResults", html)
        self.assertIn("async function loadComparison", js)
        self.assertIn("function renderComparisonRow", js)
        self.assertIn("/api/compare", js)
        self.assertIn(".compare-table", css)
        self.assertIn(".compare-pill", css)

    def test_screener_labels_recent_close_and_keeps_yield_rankings(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("最近收盤排行", html)
        self.assertIn('id="screenerPriceDate"', html)
        self.assertIn("高殖利率觀察", html)
        self.assertIn("殖利率需複查", html)
        self.assertIn("最近收盤漲跌榜", html)
        self.assertIn("收盤快照排行", html)
        self.assertIn('id="screenerTurnoverList"', html)
        self.assertIn('id="screenerVolumeList"', html)
        self.assertIn('id="screenerGapList"', html)
        self.assertIn('id="screenerAmplitudeList"', html)
        self.assertIn("function screenerPriceDate", js)
        self.assertIn("function renderScreenerSnapshotRow", js)
        self.assertIn("formatCompactAmount", js)
        self.assertIn("收盤資料", js)
        self.assertIn("均息", js)
        self.assertIn(".screener-snapshot-grid", css)

    def test_stock_page_exposes_historical_frequency_backtest(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn('id="historicalFrequency"', html)
        self.assertIn("payload.historical_frequency", js)
        self.assertIn("function renderHistoricalFrequency", js)
        self.assertIn("normal_positive_area_percent", js)
        self.assertIn(".historical-frequency-grid", css)

    def test_local_data_table_exposes_gap_status(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("資料狀態", html)
        self.assertIn("function localDataCoverageLabel", js)
        self.assertIn("dataGapShortLabel", js)
        self.assertIn(".ld-coverage", css)


if __name__ == "__main__":
    unittest.main()
