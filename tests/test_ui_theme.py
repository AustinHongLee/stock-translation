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

    def test_chart_uses_ma_warmup_prices_without_expanding_visible_prices(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("payload.ma_prices || prices", js)
        self.assertIn("function calculateAlignedMovingAverage", js)
        self.assertIn(
            "setupChart(prices, payload.chips_series || [], buildChartEvents(payload), payload.ma_prices || prices, payload.features || null)",
            js,
        )
        self.assertIn("未滿 N 根日線就不畫該條均線", js)

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

    def test_stock_page_exposes_structure_fingerprint_card(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="structureCard"', html)
        self.assertIn("structure-card", css)
        self.assertIn("structure-grid", css)
        self.assertIn("structureCard", js)
        self.assertIn("function renderStructureCard", js)
        self.assertIn("renderStructureCard(payload.structure)", js)

    def test_chart_advanced_controls_are_large_chart_only(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        tour_js = (STATIC_DIR / "chart_tour.js").read_text(encoding="utf-8")

        self.assertIn('id="chartLargeBtn"', html)
        self.assertIn('id="chartTourBtn"', html)
        self.assertIn('id="chartTourCallout"', html)
        self.assertIn('id="chartTourOverlay"', html)
        self.assertIn('id="chartIntradayBtn"', html)
        self.assertIn('id="chartIntradayBadge"', html)
        self.assertIn("大型K線圖", html)
        self.assertIn("讀圖導覽", html)
        self.assertIn("盤中暫算", html)
        self.assertIn("chart-lab-only", html)
        self.assertIn('id="chartTranslationPanel"', html)
        self.assertIn('id="chartWeatherBadge"', html)
        self.assertIn('id="chartInsightList"', html)
        self.assertIn('id="chartExplainCard"', html)
        self.assertIn('id="scenarioRangePanel"', html)
        self.assertIn("翻譯模式", html)
        self.assertIn("進階資料室", html)
        self.assertIn(".indicator-panel { display: none; }", css)
        self.assertIn(".chart-panel.chart-lab-mode .indicator-panel", css)
        self.assertIn(".chart-panel.chart-lab-mode.chart-mode-translate", css)
        self.assertIn("width: calc(100vw - 28px)", css)
        self.assertIn("height: calc(100vh - 28px)", css)
        self.assertIn(".chart-translation-panel", css)
        self.assertIn(".chart-explain-card", css)
        self.assertIn(".scenario-range-panel", css)
        self.assertIn(".indicator-data-room", css)
        self.assertIn("chartLargeMode", js)
        self.assertIn("chartOfficialAll", js)
        self.assertIn("chartOfficialStockId", js)
        self.assertIn("chartIntradayEnabled", js)
        self.assertIn("chartUxMode", js)
        self.assertIn("function toggleLargeChart", js)
        self.assertIn('window.scrollTo({ top: 0, left: 0, behavior: "auto" })', js)
        self.assertIn("window.drawChartTourOverlay", js)
        self.assertIn("window.syncChartTourUi", js)
        self.assertIn("chart_tour.js", html)
        self.assertIn("function currentTour", tour_js)
        self.assertIn("function drawChartTourOverlay", tour_js)
        self.assertIn("function drawTourAnchoredCallout", tour_js)
        self.assertIn("function chooseTourCalloutPlacement", tour_js)
        self.assertIn("function drawTourVisualGlyph", tour_js)
        self.assertIn("function drawTourReliabilityFilter", tour_js)
        self.assertIn("function updateTourDomCallout", tour_js)
        self.assertIn("function hideTourDomCallout", tour_js)
        self.assertIn("function tourCalloutText", tour_js)
        self.assertIn("function drawTourConnectionArrows", tour_js)
        self.assertIn("toggleChartTour", tour_js)
        self.assertIn("personality: \"可信度\"", tour_js)
        self.assertIn("confirm: \"確認\"", tour_js)
        self.assertIn("derivation: \"來源\"", tour_js)
        self.assertIn("progression: \"階段\"", tour_js)
        self.assertIn("chart-tour-overlay", css)
        self.assertIn(".chart-tour-callout", css)
        self.assertIn(".chart-tour-callout-leader", css)
        self.assertIn("chart-tour-readout", html)
        self.assertIn(".chart-tour-readout", css)
        self.assertIn(".chart-tour-readout h4", css)
        self.assertIn(".chart-tour-readout > p", css)
        self.assertIn(".chart-tour-readout .chart-tour-details { display: none; }", css)
        self.assertNotIn("clip-path: inset(50%)", css)
        self.assertIn("TOUR_BLUE", tour_js)
        self.assertIn("function buildIntradayChartRow", js)
        self.assertIn("function intradayChartStatusText", js)
        self.assertIn("function toggleIntradayChartLayer", js)
        self.assertIn("function refreshIntradayChartLayer", js)
        self.assertIn("function setChartUxMode", js)
        self.assertIn("function renderChartTranslation", js)
        self.assertIn("function showChartLayerExplanation", js)
        self.assertIn("function renderScenarioRange", js)
        self.assertIn("function chartScenarioFanData", js)
        self.assertIn("function drawScenarioFan", js)
        self.assertIn("function drawHoverFeatureBadge", js)
        self.assertIn("function collectIndicatorOpenState", js)
        self.assertIn("function subplotAxisDefaults", js)
        self.assertIn("function findSupportResistanceLine", js)
        self.assertIn("state.chartHoverFeatureKey", js)
        self.assertIn("if (!state.chartLargeMode) return [];", js)
        self.assertIn("圖層控制與全部指標讀值", html)
        self.assertIn("function isChartVisualFeature", js)
        self.assertIn("filter(isChartVisualFeature)", js)
        self.assertIn("renderIndicatorDataRoom", js)
        self.assertIn("function chartVolumeLayerEnabled", js)
        self.assertIn('feature.display_type === "subplot"', js)
        self.assertIn("!CHART_VOLUME_MA_KEYS.includes(feature.key)", js)
        self.assertIn("歷史範圍", js)
        self.assertIn("非預測", js)
        self.assertIn("近${windowSize}日", js)
        self.assertIn("收盤後可能改變", js)
        self.assertIn("quoteStockId && expectedStockId", js)
        self.assertIn("dateText <= lastOfficialDate", js)
        self.assertIn("正式日線已含此日期", js)
        self.assertIn("TWSE_MIS_INTRADAY", js)
        self.assertIn("provisional: true", js)
        self.assertIn("if (isIntradayOverlayActive()) return null;", js)
        self.assertIn(".chart-intraday-badge", css)

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
        self.assertIn("更新雷達只更新排行榜快照", html)
        self.assertIn("不補個股日線或法人", html)
        self.assertIn("最近收盤漲跌榜", html)
        self.assertIn("收盤快照排行", html)
        self.assertIn("市場心智雷達", html)
        self.assertIn('id="marketRadarPanel"', html)
        self.assertIn('id="marketRadarBody"', html)
        self.assertIn('id="marketRadarStatus"', html)
        self.assertIn('id="screenerSnapshotPanel"', html)
        self.assertIn('id="screenerTurnoverList"', html)
        self.assertIn('id="screenerVolumeList"', html)
        self.assertIn('id="screenerGapList"', html)
        self.assertIn('id="screenerAmplitudeList"', html)
        self.assertIn("/api/market/radar", js)
        self.assertIn("function renderMarketRadar", js)
        self.assertIn("marketRadarMeterPercent", js)
        self.assertIn("function screenerPriceDate", js)
        self.assertIn("function renderScreenerSnapshotRow", js)
        self.assertIn("formatCompactAmount", js)
        self.assertIn("收盤資料", js)
        self.assertIn("日線、法人與波段關卡仍以", js)
        self.assertIn("均息", js)
        self.assertIn(".market-radar-panel", css)
        self.assertIn(".market-radar-card", css)
        self.assertIn(".screener-snapshot-grid", css)

    def test_dividend_assumption_note_discloses_stock_dividend_scope(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("stock_dividend_scope_note", js)
        self.assertIn("function buildDividendAssumptionNote", js)

    def test_stock_page_exposes_historical_frequency_backtest(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn('id="historicalFrequency"', html)
        self.assertIn("payload.historical_frequency", js)
        self.assertIn("function renderHistoricalFrequency", js)
        self.assertIn("normal_positive_area_percent", js)
        self.assertIn("不代表後續走勢", js)
        self.assertIn("鐘形假設", js)
        self.assertIn("不當成未來機率", js)
        self.assertNotIn("常態面積", js)
        self.assertIn(".historical-frequency-grid", css)
        self.assertIn(".historical-current-note", css)

    def test_local_data_table_exposes_gap_status(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn("資料狀態", html)
        self.assertIn("雷達中心是另一份排行榜快照", html)
        self.assertIn("不會重建雷達排行榜快照", html)
        self.assertIn("function localDataTargetSummary", js)
        self.assertIn("最近收盤目標", js)
        self.assertIn("補正目標", js)
        self.assertIn("function localDataCoverageLabel", js)
        self.assertIn("dataGapShortLabel", js)
        self.assertIn("快照待更新", js)
        self.assertIn(".ld-coverage", css)
        self.assertIn(".ld-snapshot", css)


if __name__ == "__main__":
    unittest.main()
