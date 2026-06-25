// app.js 分區地圖（暫不拆檔）：state/elements/bootstrap → 資料載入 → 各頁 render →
// 圖表互動 → bulk/local-data → 共用格式與狀態元件。HTML 仍有 inline onclick，
// 未導入打包器前先維持單檔，避免模組拆分造成全域函式斷線。
const state = {
  activeSheet: "dashboard",
  activeStockId: null,
  activeSummary: null,
  activePayload: null,
  portfolio: null,
  watchlist: [],
  comparison: null,
  screener: null,
  marketRadar: null,
  screenerFilter: "value",
  localDataSort: "stock_id",
  localDataFilter: "all",
  levelsSyncing: false,
  syncing: false,
  syncStepTimer: null,
  searchTimer: null,
  searchRequestSeq: 0,
  quoteTimer: null,
  chartPrices: [],
  chartOfficialAll: [],
  chartOfficialStockId: null,
  chartIntradayEnabled: false,
  chartIntradayRow: null,
  activeQuote: null,
  chartHoverIndex: null,
  chartFeatures: null,
  chartCatalog: null,
  chartIndicatorEnabled: {},
  chartPrefs: null,
  chartAnnotations: [],
  chartHeight: "standard",
  chartScale: "price",
  chartLargeMode: false,
  chartUxMode: "translate",
  chartHoverFeatureKey: null,
  chartHoverFeatureIndex: null,
  chartHoverPoint: null,
  chartSRLines: [],
  chartPrefsTimer: null,
  glossary: {
    entries: new Map(),
    aliases: new Map(),
    patterns: [],
  },
};

const STOCK_SYNC_LOOKBACK_DAYS = 365 * 5;
const LEVEL_SYNC_CONCURRENCY = 2;
const NEWBIE_GUIDE_STORAGE_KEY = "stockTranslator.newbieGuideDismissed";
const THEME_STORAGE_KEY = "stockTranslator.theme";
const SYNC_STEPS = [
  ["公司資料", "確認股票代號、名稱與市場。"],
  ["股利資料", "抓最近股利與歷史除息紀錄。"],
  ["日線價格", "抓近 5 年日成交資料。"],
  ["估值資料", "抓本益比、殖利率與股價淨值比。"],
  ["營收財報", "補每月營收與最近財報。"],
  ["等待資料源", "如果停在這裡，通常是後端還在等證交所回應或重試。"],
  ["整理畫面", "資料回來後才會產生白話摘要，這一步本身很快。"],
];

const elements = {
  dataStatus: document.querySelector("#dataStatus"),
  navButtons: document.querySelectorAll("[data-nav-button]"),
  sheetTriggers: document.querySelectorAll("[data-sheet-target]"),
  searchForm: document.querySelector("#searchForm"),
  searchInput: document.querySelector("#searchInput"),
  searchSuggestions: document.querySelector("#searchSuggestions"),
  themeToggle: document.querySelector("#themeToggle"),
  themeColorMeta: document.querySelector('meta[name="theme-color"]'),
  localStocks: document.querySelector("#localStocks"),
  refreshLocalButton: document.querySelector("#refreshLocalButton"),
  localDataSort: document.querySelector("#localDataSort"),
  localDataFilters: document.querySelectorAll("[data-local-filter]"),
  dashboardSheet: document.querySelector("#dashboardSheet"),
  dashboardGreeting: document.querySelector("#dashboardGreeting"),
  dashboardTotalValue: document.querySelector("#dashboardTotalValue"),
  dashboardReturn: document.querySelector("#dashboardReturn"),
  dashboardAlerts: document.querySelector("#dashboardAlerts"),
  dashboardBrief: document.querySelector("#dashboardBrief"),
  dashboardHoldings: document.querySelector("#dashboardHoldings"),
  dashboardWatchlist: document.querySelector("#dashboardWatchlist"),
  dashboardRefreshButton: document.querySelector("#dashboardRefreshButton"),
  compareForm: document.querySelector("#compareForm"),
  compareInput: document.querySelector("#compareInput"),
  compareSubmitButton: document.querySelector("#compareSubmitButton"),
  compareWatchlistButton: document.querySelector("#compareWatchlistButton"),
  compareStatus: document.querySelector("#compareStatus"),
  compareResults: document.querySelector("#compareResults"),
  quickSyncButton: document.querySelector("#quickSyncButton"),
  screenerSheet: document.querySelector("#screenerSheet"),
  dataSheet: document.querySelector("#dataSheet"),
  localDataRows: document.querySelector("#localDataRows"),
  localDataSummary: document.querySelector("#localDataSummary"),
  levelsRadarList: document.querySelector("#levelsRadarList"),
  levelsSyncButton: document.querySelector("#levelsSyncButton"),
  levelsSyncStatus: document.querySelector("#levelsSyncStatus"),
  screenerIllustration: document.querySelector("#screenerIllustration"),
  screenerRadarImage: document.querySelector("#screenerRadarImage"),
  screenerStatus: document.querySelector("#screenerStatus"),
  refreshScreenerButton: document.querySelector("#refreshScreenerButton"),
  screenerExportButton: document.querySelector("#screenerExportButton"),
  newsStatus: document.querySelector("#newsStatus"),
  newsOverall: document.querySelector("#newsOverall"),
  newsList: document.querySelector("#newsList"),
  newsChip: document.querySelector("#newsChip"),
  newsChipText: document.querySelector("#newsChipText"),
  newsChipTop: document.querySelector("#newsChipTop"),
  newsSummaryRiskRadar: document.querySelector("#newsSummaryRiskRadar"),
  newsRiskRadar: document.querySelector("#newsRiskRadar"),
  chipsCard: document.querySelector("#chipsCard"),
  assessmentCard: document.querySelector("#assessmentCard"),
  loadChipsButton: document.querySelector("#loadChipsButton"),
  screenerAvailable: document.querySelector("#screenerAvailable"),
  screenerBelowCheap: document.querySelector("#screenerBelowCheap"),
  screenerNearCheap: document.querySelector("#screenerNearCheap"),
  screenerComplete: document.querySelector("#screenerComplete"),
  screenerUpdatedAt: document.querySelector("#screenerUpdatedAt"),
  screenerPriceDate: document.querySelector("#screenerPriceDate"),
  screenerHighConfList: document.querySelector("#screenerHighConfList"),
  screenerLowConfList: document.querySelector("#screenerLowConfList"),
  screenerLowConfCard: document.querySelector("#screenerLowConfCard"),
  screenerLowConfToggleRow: document.querySelector("#screenerLowConfToggleRow"),
  screenerLowConfToggle: document.querySelector("#screenerLowConfToggle"),
  screenerLowConfCount: document.querySelector("#screenerLowConfCount"),
  screenerYieldList: document.querySelector("#screenerYieldList"),
  screenerTrapList: document.querySelector("#screenerTrapList"),
  screenerTrapCard: document.querySelector("#screenerTrapCard"),
  screenerGainersList: document.querySelector("#screenerGainersList"),
  screenerLosersList: document.querySelector("#screenerLosersList"),
  screenerTurnoverList: document.querySelector("#screenerTurnoverList"),
  screenerVolumeList: document.querySelector("#screenerVolumeList"),
  screenerGapList: document.querySelector("#screenerGapList"),
  screenerAmplitudeList: document.querySelector("#screenerAmplitudeList"),
  marketRadarPanel: document.querySelector("#marketRadarPanel"),
  marketRadarStatus: document.querySelector("#marketRadarStatus"),
  marketRadarBody: document.querySelector("#marketRadarBody"),
  message: document.querySelector("#message"),
  portfolioStatus: document.querySelector("#portfolioStatus"),
  portfolioSentence: document.querySelector("#portfolioSentence"),
  portfolioPositionCount: document.querySelector("#portfolioPositionCount"),
  portfolioCostBasis: document.querySelector("#portfolioCostBasis"),
  portfolioMarketValue: document.querySelector("#portfolioMarketValue"),
  portfolioUnrealized: document.querySelector("#portfolioUnrealized"),
  portfolioRealized: document.querySelector("#portfolioRealized"),
  portfolioCashDividends: document.querySelector("#portfolioCashDividends"),
  portfolioTotalReturn: document.querySelector("#portfolioTotalReturn"),
  portfolioXirr: document.querySelector("#portfolioXirr"),
  portfolioBenchmark: document.querySelector("#portfolioBenchmark"),
  portfolioForm: document.querySelector("#portfolioForm"),
  portfolioTransactionId: document.querySelector("#portfolioTransactionId"),
  portfolioStockId: document.querySelector("#portfolioStockId"),
  portfolioTradeDate: document.querySelector("#portfolioTradeDate"),
  portfolioSide: document.querySelector("#portfolioSide"),
  portfolioShares: document.querySelector("#portfolioShares"),
  portfolioPrice: document.querySelector("#portfolioPrice"),
  portfolioFee: document.querySelector("#portfolioFee"),
  portfolioTax: document.querySelector("#portfolioTax"),
  portfolioNote: document.querySelector("#portfolioNote"),
  portfolioStockSuggest: document.querySelector("#portfolioStockSuggest"),
  portfolioPriceHint: document.querySelector("#portfolioPriceHint"),
  portfolioSubmitButton: document.querySelector("#portfolioSubmitButton"),
  portfolioResetButton: document.querySelector("#portfolioResetButton"),
  portfolioRows: document.querySelector("#portfolioRows"),
  portfolioTransactionRows: document.querySelector("#portfolioTransactionRows"),
  portfolioTransactionCount: document.querySelector("#portfolioTransactionCount"),
  portfolioLimitations: document.querySelector("#portfolioLimitations"),
  portfolioExpertChecks: document.querySelector("#portfolioExpertChecks"),
  portfolioExportButton: document.querySelector("#portfolioExportButton"),
  portfolioPanel: document.querySelector("#portfolioPanel"),
  emptyState: document.querySelector("#emptyState"),
  stockView: document.querySelector("#stockView"),
  stockFocus: document.querySelector("#stockFocus"),
  stockMarket: document.querySelector("#stockMarket"),
  stockTitle: document.querySelector("#stockTitle"),
  stockHeaderPrice: document.querySelector("#stockHeaderPrice"),
  stockHeaderChange: document.querySelector("#stockHeaderChange"),
  stockHeaderPriceLabel: document.querySelector("#stockHeaderPriceLabel"),
  structureCard: document.querySelector("#structureCard"),
  etfNote: document.querySelector("#etfNote"),
  stockSubtitle: document.querySelector("#stockSubtitle"),
  stockDataNote: document.querySelector("#stockDataNote"),
  syncProgressPanel: document.querySelector("#syncProgressPanel"),
  syncProgressTitle: document.querySelector("#syncProgressTitle"),
  syncProgressDetail: document.querySelector("#syncProgressDetail"),
  syncProgressSteps: document.querySelector("#syncProgressSteps"),
  syncButton: document.querySelector("#syncButton"),
  watchlistButton: document.querySelector("#watchlistButton"),
  buyStockButton: document.querySelector("#buyStockButton"),
  stockExportButton: document.querySelector("#stockExportButton"),
  stockReportButton: document.querySelector("#stockReportButton"),
  newbieGuideButton: document.querySelector("#newbieGuideButton"),
  newbieGuideCard: document.querySelector("#newbieGuideCard"),
  newbieGuideClose: document.querySelector("#newbieGuideClose"),
  quoteStatus: document.querySelector("#quoteStatus"),
  quotePriceLabel: document.querySelector("#quotePriceLabel"),
  quotePrice: document.querySelector("#quotePrice"),
  quoteTime: document.querySelector("#quoteTime"),
  quoteChangeLabel: document.querySelector("#quoteChangeLabel"),
  quoteChange: document.querySelector("#quoteChange"),
  quotePreviousClose: document.querySelector("#quotePreviousClose"),
  quoteDayRange: document.querySelector("#quoteDayRange"),
  quoteOpen: document.querySelector("#quoteOpen"),
  quoteBidAsk: document.querySelector("#quoteBidAsk"),
  quoteSpread: document.querySelector("#quoteSpread"),
  quoteNote: document.querySelector("#quoteNote"),
  companyBriefTitle: document.querySelector("#companyBriefTitle"),
  companyBriefText: document.querySelector("#companyBriefText"),
  companyRiskTags: document.querySelector("#companyRiskTags"),
  companyBriefAdvice: document.querySelector("#companyBriefAdvice"),
  latestClose: document.querySelector("#latestClose"),
  dailyChangeLabel: document.querySelector("#dailyChangeLabel"),
  dailyChange: document.querySelector("#dailyChange"),
  pricePosition: document.querySelector("#pricePosition"),
  rowCount: document.querySelector("#rowCount"),
  revenueStatus: document.querySelector("#revenueStatus"),
  revenueSummaryTitle: document.querySelector("#revenueSummaryTitle"),
  revenueSummaryValue: document.querySelector("#revenueSummaryValue"),
  revenueSummaryText: document.querySelector("#revenueSummaryText"),
  revenueMom: document.querySelector("#revenueMom"),
  revenueYoy: document.querySelector("#revenueYoy"),
  revenueCumulativeYoy: document.querySelector("#revenueCumulativeYoy"),
  revenueRows: document.querySelector("#revenueRows"),
  financialStatus: document.querySelector("#financialStatus"),
  financialSummaryTitle: document.querySelector("#financialSummaryTitle"),
  financialSummaryValue: document.querySelector("#financialSummaryValue"),
  financialSummaryText: document.querySelector("#financialSummaryText"),
  netMargin: document.querySelector("#netMargin"),
  roeValue: document.querySelector("#roeValue"),
  roaValue: document.querySelector("#roaValue"),
  financialRows: document.querySelector("#financialRows"),
  fundamentalTrends: document.querySelector("#fundamentalTrends"),
  historicalFrequency: document.querySelector("#historicalFrequency"),
  priceChartTitle: document.querySelector("#priceChartTitle"),
  dateRange: document.querySelector("#dateRange"),
  chartLargeBtn: document.querySelector("#chartLargeBtn"),
  chartTourBtn: document.querySelector("#chartTourBtn"),
  chartIntradayBtn: document.querySelector("#chartIntradayBtn"),
  chartIntradayBadge: document.querySelector("#chartIntradayBadge"),
  chartHeightSelect: document.querySelector("#chartHeightSelect"),
  chartScaleSelect: document.querySelector("#chartScaleSelect"),
  chartRangeBtn: document.querySelector("#chartRangeBtn"),
  chartClearRangeBtn: document.querySelector("#chartClearRangeBtn"),
  chartTranslationPanel: document.querySelector("#chartTranslationPanel"),
  chartWeatherBadge: document.querySelector("#chartWeatherBadge"),
  chartTranslationLine: document.querySelector("#chartTranslationLine"),
  chartInsightList: document.querySelector("#chartInsightList"),
  chartExplainCard: document.querySelector("#chartExplainCard"),
  scenarioRangePanel: document.querySelector("#scenarioRangePanel"),
  chartModeTranslateBtn: document.querySelector("#chartModeTranslateBtn"),
  chartModeAdvancedBtn: document.querySelector("#chartModeAdvancedBtn"),
  indicatorPresets: document.querySelector("#indicatorPresets"),
  indicatorGroups: document.querySelector("#indicatorGroups"),
  experimentalNotice: document.querySelector("#experimentalNotice"),
  annotationKind: document.querySelector("#annotationKind"),
  annotationText: document.querySelector("#annotationText"),
  annotationAddBtn: document.querySelector("#annotationAddBtn"),
  annotationList: document.querySelector("#annotationList"),
  rangeStatsPanel: document.querySelector("#rangeStatsPanel"),
  validationItems: document.querySelector("#validationItems"),
  reportEngine: document.querySelector("#reportEngine"),
  healthReport: document.querySelector("#healthReport"),
  reportDisclaimer: document.querySelector("#reportDisclaimer"),
  avgCashDividend: document.querySelector("#avgCashDividend"),
  dividendCoverage: document.querySelector("#dividendCoverage"),
  peRatio: document.querySelector("#peRatio"),
  marketDate: document.querySelector("#marketDate"),
  marketYield: document.querySelector("#marketYield"),
  valuationSuitability: document.querySelector("#valuationSuitability"),
  valuationBands: document.querySelector("#valuationBands"),
  relativeValuation: document.querySelector("#relativeValuation"),
  valuationDividendBody: document.querySelector("#valuationDividendBody"),
  valuationEstimates: document.querySelector("#valuationEstimates"),
  dividendAssumptionNote: document.querySelector("#dividendAssumptionNote"),
  historicalYieldStatus: document.querySelector("#historicalYieldStatus"),
  historicalYieldGrid: document.querySelector("#historicalYieldGrid"),
  valuationWarning: document.querySelector("#valuationWarning"),
  dividendRows: document.querySelector("#dividendRows"),
  latestNote: document.querySelector("#latestNote"),
  priceRows: document.querySelector("#priceRows"),
  priceChart: document.querySelector("#priceChart"),
  eventDate: document.querySelector("#eventDate"),
  eventSummary: document.querySelector("#eventSummary"),
  eventClose: document.querySelector("#eventClose"),
  eventDayChange: document.querySelector("#eventDayChange"),
  eventVolume: document.querySelector("#eventVolume"),
  eventVolumeSignal: document.querySelector("#eventVolumeSignal"),
  eventItems: document.querySelector("#eventItems"),
  eventNewsLink: document.querySelector("#eventNewsLink"),
  glossaryOverlay: document.querySelector("#glossaryOverlay"),
  glossaryClose: document.querySelector("#glossaryClose"),
  glossaryTitle: document.querySelector("#glossaryTitle"),
  glossaryPlain: document.querySelector("#glossaryPlain"),
  glossaryHow: document.querySelector("#glossaryHow"),
  glossaryGuide: document.querySelector("#glossaryGuide"),
};

applyTheme(getInitialTheme(), { persist: false, redraw: false });
setupStockFocusLayout();
registerServiceWorker();

elements.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = elements.searchInput.value.trim();
  if (!query) return;
  await search(query);
});

elements.sheetTriggers.forEach((button) => {
  button.addEventListener("click", () => showSheet(button.dataset.sheetTarget));
});
elements.searchInput.addEventListener("input", handleSearchInput);
elements.searchInput.addEventListener("focus", handleSearchInput);
elements.searchSuggestions.addEventListener("click", handleSearchSuggestionClick);
elements.themeToggle?.addEventListener("click", toggleTheme);
elements.refreshLocalButton.addEventListener("click", loadWatchlist);
elements.dashboardRefreshButton.addEventListener("click", loadWatchlist);
elements.dashboardWatchlist.addEventListener("click", handleDashboardStockClick);
elements.dashboardHoldings.addEventListener("click", handleDashboardStockClick);
elements.compareForm?.addEventListener("submit", handleCompareSubmit);
elements.compareWatchlistButton?.addEventListener("click", loadComparisonFromWatchlist);
elements.compareResults?.addEventListener("click", handleDashboardStockClick);
elements.quickSyncButton.addEventListener("click", () => syncStock("2330"));
elements.refreshScreenerButton.addEventListener("click", refreshValueScreener);
elements.screenerExportButton?.addEventListener("click", exportScreenerExcel);
elements.levelsSyncButton?.addEventListener("click", syncLevelsTargets);
elements.localDataSort?.addEventListener("change", () => {
  state.localDataSort = elements.localDataSort.value || "stock_id";
  renderLocalDataTable(state.localData);
});
elements.localDataFilters?.forEach((button) => {
  button.addEventListener("click", () => {
    state.localDataFilter = button.dataset.localFilter || "all";
    updateLocalDataFilterButtons();
    renderLocalDataTable(state.localData);
  });
});
// 雷達中心：列表項目點擊（事件委派）
document.querySelector("#screenerSheet").addEventListener("click", handleScreenerAction);
document.querySelector("#dataSheet")?.addEventListener("click", handleScreenerAction);
elements.portfolioForm.addEventListener("submit", savePortfolioTransaction);
elements.portfolioResetButton.addEventListener("click", resetPortfolioForm);
elements.portfolioStockId.addEventListener("input", handlePortfolioStockInput);
elements.portfolioStockId.addEventListener("change", autofillTradePrice);
elements.portfolioStockId.addEventListener("blur", () => window.setTimeout(hidePortfolioStockSuggest, 150));
elements.portfolioStockSuggest?.addEventListener("mousedown", handlePortfolioStockSuggestPick);
elements.portfolioTradeDate.addEventListener("change", autofillTradePrice);
elements.portfolioShares.addEventListener("input", autofillFeeTax);
elements.portfolioPrice.addEventListener("input", autofillFeeTax);
elements.portfolioSide.addEventListener("change", autofillFeeTax);
elements.portfolioFee.addEventListener("input", () => { state.feeManual = true; });
elements.portfolioTax.addEventListener("input", () => { state.taxManual = true; });
elements.portfolioTransactionRows.addEventListener("click", handlePortfolioTableAction);
elements.portfolioExportButton.addEventListener("click", exportPortfolioExcel);
elements.syncButton.addEventListener("click", () => {
  if (state.activeStockId) syncStock(state.activeStockId);
});
elements.watchlistButton.addEventListener("click", () => {
  if (state.activeStockId) toggleWatchlist(state.activeStockId);
});
elements.buyStockButton.addEventListener("click", () => {
  if (state.activeStockId) {
    elements.portfolioStockId.value = state.activeStockId;
  }
  showSheet("portfolio");
  window.setTimeout(() => {
    elements.portfolioForm.scrollIntoView({ behavior: "smooth", block: "center" });
    elements.portfolioStockId.focus();
  }, 0);
});
elements.stockExportButton.addEventListener("click", exportStockExcel);
elements.stockReportButton.addEventListener("click", exportStockReport);
elements.chartHeightSelect?.addEventListener("change", () => setChartHeight(elements.chartHeightSelect.value, { persist: true }));
elements.chartScaleSelect?.addEventListener("change", () => setChartScale(elements.chartScaleSelect.value, { persist: true }));
elements.indicatorGroups?.addEventListener("change", handleIndicatorToggleChange);
elements.priceChart.addEventListener("mousemove", handleChartPointerMove);
elements.priceChart.addEventListener("mouseleave", () => {
  state.chartHoverIndex = null;
  state.chartHoverFeatureKey = null;
  state.chartHoverFeatureIndex = null;
  state.chartHoverPoint = null;
  if (!state.chartSelectingRange) state.chartDragging = false;
  drawChart();
});
elements.priceChart.addEventListener("wheel", handleChartWheel, { passive: false });
elements.priceChart.addEventListener("mousedown", handleChartMouseDown);
elements.priceChart.addEventListener("click", handleChartClick);
window.addEventListener("mouseup", handleChartMouseUp);
elements.newbieGuideClose?.addEventListener("click", () => hideNewbieGuide(true));
elements.glossaryClose.addEventListener("click", hideGlossary);
elements.glossaryOverlay.addEventListener("click", (event) => {
  if (event.target === elements.glossaryOverlay) hideGlossary();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (state.chartLargeMode) toggleLargeChart(false);
    hideGlossary();
    hideSearchSuggestions();
  }
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".search-shell")) hideSearchSuggestions();
  const trigger = event.target.closest("[data-glossary-term]");
  if (!trigger) return;
  showGlossary(trigger.dataset.glossaryTerm);
});

window.addEventListener("resize", () => {
  if (state.activeStockId) {
    loadStock(state.activeStockId, { quiet: true, keepSheet: true });
  }
});

init();

async function init() {
  await loadGlossary();
  resetPortfolioForm();
  showSheet("dashboard", { preserveScroll: true });
  await loadPortfolio();
  await loadWatchlist();
  await loadDefaultComparison();
  await loadValueScreener();
  await loadMarketRadar();
  renderDashboard();
}

function setupStockFocusLayout() {
  if (!elements.stockFocus) return;
  [".focus-assess", ".focus-chart", ".focus-chips"].forEach((selector) => {
    const card = document.querySelector(selector);
    if (card && card.parentElement !== elements.stockFocus) {
      elements.stockFocus.appendChild(card);
    }
  });
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.warn("Service worker registration failed", error);
    });
  });
}

function getInitialTheme() {
  try {
    const stored = window.localStorage?.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch (error) {}
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}

function applyTheme(theme, options = {}) {
  const normalized = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalized;
  document.body.dataset.theme = normalized;
  if (elements.themeColorMeta) {
    elements.themeColorMeta.setAttribute("content", normalized === "dark" ? "#0D141C" : "#1C3D5A");
  }
  if (elements.themeToggle) {
    const label = normalized === "dark" ? "切換淺色模式" : "切換深色模式";
    elements.themeToggle.setAttribute("aria-pressed", normalized === "dark" ? "true" : "false");
    elements.themeToggle.setAttribute("aria-label", label);
    elements.themeToggle.setAttribute("title", label);
    elements.themeToggle.classList.toggle("is-dark", normalized === "dark");
  }
  if (options.persist !== false) {
    try { window.localStorage?.setItem(THEME_STORAGE_KEY, normalized); } catch (error) {}
  }
  if (options.redraw !== false) refreshThemeCanvases();
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

function refreshThemeCanvases() {
  drawChart();
  const valuation = state.activePayload?.valuation;
  if (valuation?.bands) renderValuationBands(valuation.bands);
  if (state.activeChips) renderChipsCard(state.activeChips);
}

function cssVar(name, fallback) {
  try {
    const value = window.getComputedStyle?.(document.documentElement)?.getPropertyValue(name)?.trim();
    return value || fallback;
  } catch (error) {
    return fallback;
  }
}

function chartThemeColors() {
  return {
    canvasBg: cssVar("--chart-bg", "#ffffff"),
    grid: cssVar("--chart-grid", "#e8ece8"),
    line: cssVar("--line", "#dce2e8"),
    muted: cssVar("--muted", "#6B7785"),
    muted2: cssVar("--muted-2", "#9AA6B2"),
    ink2: cssVar("--ink-2", "#33404C"),
    brand: cssVar("--brand", "#1C3D5A"),
    brand2: cssVar("--brand-2", "#2C5475"),
    warn: cssVar("--warn", "#B0820B"),
    rangeFill: cssVar("--chart-range-fill", "rgba(28, 61, 90, 0.10)"),
    rangeStroke: cssVar("--chart-range-stroke", "rgba(28, 61, 90, 0.42)"),
    tooltipBg: cssVar("--chart-tooltip-bg", "rgba(23,32,27,0.93)"),
    tooltipText: cssVar("--chart-tooltip-text", "#eef2f0"),
    tooltipAccent: cssVar("--chart-tooltip-accent", "#ffd9b0"),
  };
}

async function loadGlossary() {
  try {
    const payload = await getJson("/api/glossary");
    state.glossary.entries = new Map(payload.entries.map((entry) => [entry.term, entry]));
    state.glossary.aliases = new Map(Object.entries(payload.aliases));
    state.glossary.patterns = Array.from(state.glossary.aliases.keys())
      .sort((a, b) => b.length - a.length);
  } catch (error) {
    console.warn("Glossary unavailable", error);
  }
}

function showSheet(sheet, options = {}) {
  const target = ["dashboard", "screener", "portfolio", "stock", "data"].includes(sheet) ? sheet : "dashboard";
  state.activeSheet = target;
  document.body.dataset.sheet = target;
  const allSheets = [
    elements.dashboardSheet,
    elements.screenerSheet,
    elements.portfolioPanel,
    elements.dataSheet,
    elements.emptyState,
    elements.stockView,
  ];
  allSheets.forEach((item) => item?.classList.add("hidden"));

  let visibleSheet = elements.dashboardSheet;
  if (target === "screener") {
    visibleSheet = elements.screenerSheet;
    loadMarketRadar();
  } else if (target === "portfolio") {
    visibleSheet = elements.portfolioPanel;
  } else if (target === "stock") {
    visibleSheet = state.activePayload ? elements.stockView : elements.emptyState;
  } else if (target === "data") {
    visibleSheet = elements.dataSheet;
  }
  visibleSheet?.classList.remove("hidden");
  if (target === "data" || target === "screener") loadLocalData();

  elements.navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.sheetTarget === target);
  });

  if (!options.preserveScroll) {
    window.scrollTo({ top: 0, behavior: options.smooth ? "smooth" : "auto" });
  }
}

function newbieGuideDismissed() {
  try {
    return window.localStorage?.getItem(NEWBIE_GUIDE_STORAGE_KEY) === "1";
  } catch (error) {
    return false;
  }
}

function maybeShowNewbieGuide() {
  if (!elements.newbieGuideCard) return;
  if (newbieGuideDismissed()) {
    elements.newbieGuideCard.classList.add("hidden");
    return;
  }
  showNewbieGuide(false);
}

function showNewbieGuide(force = false) {
  if (!elements.newbieGuideCard) return;
  elements.newbieGuideCard.classList.remove("hidden");
  if (force) {
    try { window.localStorage?.removeItem(NEWBIE_GUIDE_STORAGE_KEY); } catch (error) {}
  }
}

function hideNewbieGuide(persist = false) {
  if (!elements.newbieGuideCard) return;
  elements.newbieGuideCard.classList.add("hidden");
  if (persist) {
    try { window.localStorage?.setItem(NEWBIE_GUIDE_STORAGE_KEY, "1"); } catch (error) {}
  }
}

function handleSearchInput() {
  const query = elements.searchInput.value.trim();
  window.clearTimeout(state.searchTimer);
  if (!query) {
    hideSearchSuggestions();
    return;
  }
  state.searchTimer = window.setTimeout(() => loadSearchSuggestions(query), 180);
}

async function loadSearchSuggestions(query) {
  const requestSeq = ++state.searchRequestSeq;
  try {
    const payload = await getJson(`/api/search?q=${encodeURIComponent(query)}`);
    if (requestSeq !== state.searchRequestSeq) return;
    renderSearchSuggestions(payload);
  } catch (error) {
    elements.searchSuggestions.innerHTML = `<div class="suggestion-empty">搜尋暫時失敗：${escapeHtml(error.message)}</div>`;
    elements.searchSuggestions.classList.remove("hidden");
  }
}

function renderSearchSuggestions(payload) {
  const results = payload.results || [];
  if (!results.length && !payload.can_sync) {
    elements.searchSuggestions.innerHTML = `<div class="suggestion-empty">找不到相似股票。可輸入完整股票代號同步。</div>`;
    elements.searchSuggestions.classList.remove("hidden");
    return;
  }

  const rows = results.slice(0, 8).map((item) => `
    <button class="suggestion-item" type="button" ${item.is_local ? `data-stock-id="${escapeHtml(item.stock_id)}"` : `data-sync-stock="${escapeHtml(item.stock_id)}"`}>
      <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || item.name || "")}</strong>
      <span>${escapeHtml(searchSuggestionMeta(item))}</span>
    </button>
  `);
  if (payload.can_sync) {
    rows.push(`
      <button class="suggestion-item suggestion-sync" type="button" data-sync-stock="${escapeHtml(payload.query)}">
        <strong>同步 ${escapeHtml(payload.query)}</strong>
        <span>本地找不到時，抓取近 5 年資料</span>
      </button>
    `);
  }
  elements.searchSuggestions.innerHTML = rows.join("");
  elements.searchSuggestions.classList.remove("hidden");
}

function searchSuggestionMeta(item) {
  const name = item.name && item.name !== item.short_name ? ` · ${item.name}` : "";
  if (item.is_local) return `已下載，可直接開啟${name}`;
  return `股票名錄有這檔，點選後先同步資料${name}`;
}

function hideSearchSuggestions() {
  elements.searchSuggestions.classList.add("hidden");
}

async function handleSearchSuggestionClick(event) {
  const button = event.target.closest("button");
  if (!button) return;
  const stockId = button.dataset.stockId;
  const syncStockId = button.dataset.syncStock;
  hideSearchSuggestions();
  elements.searchInput.value = "";
  if (stockId) {
    await loadStock(stockId);
    return;
  }
  if (syncStockId) {
    await syncStock(syncStockId);
  }
}

async function search(query) {
  showMessage("搜尋中...");
  hideSearchSuggestions();
  try {
    const payload = await getJson(`/api/search?q=${encodeURIComponent(query)}`);
    if (payload.results.length > 0) {
      const first = payload.results[0];
      const stockId = first.stock_id;
      hideMessage();
      if (first.is_local) {
        await loadStock(stockId);
      } else {
        await syncStock(stockId, {
          label: `${stockId} ${first.short_name || first.name || ""}`.trim(),
        });
      }
      elements.searchInput.value = "";
      return;
    }
    if (payload.can_sync) {
      await syncStock(query);
      elements.searchInput.value = "";
      return;
    }
    showMessage("本地找不到這個名稱；請先用股票代號同步。", true);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function loadWatchlist() {
  try {
    const payload = await getJson("/api/watchlist");
    state.watchlist = payload.items || [];
    elements.localStocks.innerHTML = "";
    elements.dataStatus.textContent = `${payload.items.length} 支自選股`;
    if (payload.items.length === 0) {
      elements.localStocks.innerHTML = stateMessageHTML("empty", "尚未加入自選股", "查到股票後可以加入觀察。", {
        compact: true,
        className: "empty-local",
      });
      renderDashboard();
      return;
    }
    for (const item of payload.items) {
      const profile = item.profile || {
        stock_id: item.stock_id,
        short_name: item.stock_id,
        name: item.stock_id,
      };
      const latest = item.latest;
      const button = document.createElement("button");
      button.className = "stock-item";
      button.type = "button";
      button.dataset.stockId = profile.stock_id;
      button.innerHTML = `
        <strong>${escapeHtml(profile.stock_id)} ${escapeHtml(profile.short_name)}</strong>
        <span>${latest ? `收盤 ${formatNumber(latest.close)} · ${escapeHtml(latest.date)}` : "尚無日線，請同步"}</span>
        <span>${item.rows} 筆 · 已加入自選</span>
      `;
      button.addEventListener("click", () => loadStock(profile.stock_id));
      elements.localStocks.appendChild(button);
    }
    markActiveStock();
    renderDashboard();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function loadDefaultComparison() {
  if (!elements.compareResults) return;
  const ids = comparisonIdsFromWatchlist();
  if (ids.length >= 2) {
    if (elements.compareInput && !elements.compareInput.value.trim()) {
      elements.compareInput.value = ids.join(", ");
    }
    await loadComparison(ids, { quiet: true });
    return;
  }
  renderComparisonPlaceholder();
}

async function loadComparisonFromWatchlist() {
  const ids = comparisonIdsFromWatchlist();
  if (ids.length < 2) {
    renderComparisonMessage("empty", "自選股不足", "至少需要 2 檔自選股才能做多股比較。");
    return;
  }
  if (elements.compareInput) elements.compareInput.value = ids.join(", ");
  await loadComparison(ids);
}

async function handleCompareSubmit(event) {
  event.preventDefault();
  const ids = comparisonInputIds();
  if (ids.length < 2) {
    renderComparisonMessage("empty", "目標不足", "請輸入 2–3 檔股票代號。");
    return;
  }
  await loadComparison(ids);
}

async function loadComparison(ids, options = {}) {
  const targets = uniqueStockIds(ids).slice(0, 3);
  if (targets.length < 2) {
    renderComparisonPlaceholder();
    return;
  }
  if (elements.compareSubmitButton) elements.compareSubmitButton.disabled = true;
  if (elements.compareWatchlistButton) elements.compareWatchlistButton.disabled = true;
  if (elements.compareStatus) elements.compareStatus.textContent = `比較中 ${targets.length} 檔`;
  if (!options.quiet) {
    renderComparisonMessage("loading", "比較中", targets.join(" / "));
  }
  try {
    const payload = await getJson(`/api/compare?stock_ids=${encodeURIComponent(targets.join(","))}`);
    state.comparison = payload;
    if (elements.compareInput) {
      elements.compareInput.value = (payload.requested || targets).join(", ");
    }
    renderComparison(payload);
  } catch (error) {
    renderComparisonMessage("error", "比較失敗", error.message || "請稍後再試。");
    if (elements.compareStatus) elements.compareStatus.textContent = "讀取失敗";
  } finally {
    if (elements.compareSubmitButton) elements.compareSubmitButton.disabled = false;
    if (elements.compareWatchlistButton) elements.compareWatchlistButton.disabled = false;
  }
}

function comparisonIdsFromWatchlist() {
  return uniqueStockIds(
    (state.watchlist || []).map((item) => item.profile?.stock_id || item.stock_id)
  ).slice(0, 3);
}

function comparisonInputIds() {
  const raw = elements.compareInput?.value || "";
  return uniqueStockIds(raw.split(/[\s,，、/|]+/)).slice(0, 3);
}

function renderComparisonPlaceholder() {
  if (elements.compareStatus) elements.compareStatus.textContent = "輸入 2–3 檔";
  renderComparisonMessage("empty", "等待比較目標", "加入至少 2 檔自選股，或輸入股票代號。");
}

function renderComparisonMessage(kind, title, body) {
  if (!elements.compareResults) return;
  elements.compareResults.innerHTML = stateMessageHTML(kind, title, body, {
    compact: true,
    className: "compare-empty",
  });
}

function renderComparison(payload) {
  if (!elements.compareResults) return;
  const items = payload?.items || [];
  if (items.length < 2) {
    renderComparisonPlaceholder();
    return;
  }
  if (elements.compareStatus) {
    elements.compareStatus.textContent = `${items.length} 檔 · 本地資料`;
  }
  elements.compareResults.innerHTML = `
    <div class="table-wrap compare-table-wrap">
      <table class="compare-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>價格</th>
            <th>三大法人</th>
            <th>體質</th>
            <th>財報點</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${items.map(renderComparisonRow).join("")}</tbody>
      </table>
    </div>
  `;
}

function renderComparisonRow(item) {
  const profile = item.profile || { stock_id: item.stock_id, short_name: item.stock_id };
  const price = item.price || {};
  const chips = item.chips || {};
  const assessment = item.assessment || {};
  const financial = item.financial || {};
  const stockId = profile.stock_id || item.stock_id || "";
  const label = `${stockId} ${profile.short_name || profile.name || ""}`.trim();
  const priceText = price.latest_close == null ? "--" : formatNumber(price.latest_close);
  const changeText = price.change_percent == null ? "--" : formatPercent(price.change_percent);
  const positionText = price.window_position_percent == null
    ? "區間位置 --"
    : `區間位置 ${formatPlainPercent(price.window_position_percent)}`;
  const chipsText = chips.sum_20_lots == null ? "待同步" : `${formatSignedLots(chips.sum_20_lots)} / 20日`;
  const chipsMeta = chips.as_of ? `${chips.level || "無"} · ${chips.as_of}` : "法人資料待補";
  const assessMeta = assessment.available
    ? `多 ${assessment.bull || 0} / 空 ${assessment.bear || 0} / 中 ${assessment.neutral || 0}`
    : "日線不足";
  const financialText = financial.available
    ? `EPS ${formatNumber(financial.eps)} · ROE ${formatPercent(financial.roe_percent)}`
    : "財報待補";
  const financialMeta = financial.quarter || financial.title || "--";
  return `
    <tr>
      <td data-label="股票">
        <button class="compare-stock-link" type="button" data-stock-id="${escapeHtml(stockId)}">${escapeHtml(label)}</button>
        <span class="compare-meta">${price.date ? `資料日 ${escapeHtml(price.date)}` : "日線待補"}</span>
      </td>
      <td data-label="價格">
        <strong class="${toneClass(price.change_percent)}">${escapeHtml(priceText)}</strong>
        <span class="compare-meta ${toneClass(price.change_percent)}">${escapeHtml(changeText)}</span>
        <span class="compare-meta">${escapeHtml(positionText)}</span>
      </td>
      <td data-label="三大法人">
        <strong class="${toneClass(chips.sum_20_lots)}">${escapeHtml(chipsText)}</strong>
        <span class="compare-meta">${escapeHtml(chipsMeta)}</span>
      </td>
      <td data-label="體質">
        <span class="compare-pill tone-${escapeHtml(assessment.tone || "unknown")}">${escapeHtml(assessment.label || "--")}</span>
        <span class="compare-meta">${escapeHtml(assessMeta)}</span>
      </td>
      <td data-label="財報點">
        <strong class="tone-${escapeHtml(financial.tone || "unknown")}">${escapeHtml(financialText)}</strong>
        <span class="compare-meta">${escapeHtml(financialMeta)}</span>
      </td>
      <td data-label="操作">
        <button class="table-action" type="button" data-stock-id="${escapeHtml(stockId)}">看個股</button>
      </td>
    </tr>
  `;
}

function formatSignedLots(value) {
  if (value == null) return "--";
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (number === 0) return "0 張";
  const sign = number > 0 ? "+" : "-";
  return `${sign}${formatInteger(Math.abs(number))} 張`;
}

async function loadValueScreener() {
  try {
    const payload = await getJson("/api/value-screener");
    state.screener = payload;
    renderScreener(payload);
  } catch (error) {
    elements.screenerStatus.textContent = `雷達中心讀取失敗：${error.message}`;
  }
}

async function loadMarketRadar() {
  if (!elements.marketRadarBody) return;
  try {
    const payload = await getJson("/api/market/radar");
    state.marketRadar = payload;
    renderMarketRadar(payload);
  } catch (error) {
    if (elements.marketRadarStatus) elements.marketRadarStatus.textContent = `市場心智雷達讀取失敗：${error.message}`;
    elements.marketRadarBody.innerHTML = stateMessageHTML("error", "讀取失敗", "稍後再試，或先確認本地資料庫可讀。", {
      compact: true,
      className: "screener-empty",
    });
  }
}

function renderMarketRadar(payload) {
  if (!elements.marketRadarBody) return;
  const metrics = Array.isArray(payload?.metrics) ? payload.metrics : [];
  if (elements.marketRadarStatus) {
    elements.marketRadarStatus.textContent = payload?.available
      ? `${payload.title || "市場心智雷達"} · 資料日 ${payload.as_of_date || "--"} · 宇宙 ${formatInteger(payload.universe_size || 0)} 檔 · ${payload.window || 120} 日視窗`
      : payload?.reason || "資料不足，請先在本地資料完成全市場下載。";
  }
  if (!payload?.available || !metrics.length) {
    elements.marketRadarBody.innerHTML = `
      ${stateMessageHTML("empty", "資料不足", payload?.reason || "請先在本地資料完成全市場下載。", {
        compact: true,
        className: "screener-empty",
      })}
      <button class="secondary-button market-radar-cta" type="button" onclick="showSheet('data')">去本地資料下載</button>
    `;
    return;
  }
  elements.marketRadarBody.innerHTML = metrics.map(renderMarketRadarMetric).join("");
}

function renderMarketRadarMetric(metric) {
  const value = Number(metric?.value);
  const percent = marketRadarMeterPercent(metric);
  const valueText = Number.isFinite(value)
    ? (metric.key === "dispersion" ? `${(value * 100).toFixed(2)}%` : value.toFixed(2))
    : "--";
  const label = metric?.glossary_term
    ? `<button class="term-link" type="button" data-glossary-term="${escapeHtml(metric.glossary_term)}">${escapeHtml(metric.label || metric.key || "--")}</button>`
    : escapeHtml(metric?.label || metric?.key || "--");
  return `
    <article class="market-radar-card" title="${escapeHtml(metric?.forbidden || "")}">
      <div class="market-radar-card-head">
        <h4>${label}</h4>
        <strong>${escapeHtml(valueText)}</strong>
      </div>
      <div class="market-radar-meter" aria-label="${escapeHtml(metric?.label || "")}">
        <span style="width:${percent}%"></span>
      </div>
      <p>${escapeHtml(metric?.summary || "--")}</p>
      <small>${escapeHtml(metric?.forbidden || "不得當成方向或操作訊號。")}</small>
    </article>
  `;
}

function marketRadarMeterPercent(metric) {
  if (metric?.key === "dispersion" && metric.percentile != null) {
    return Math.max(3, Math.min(100, Number(metric.percentile)));
  }
  const value = Number(metric?.value);
  if (!Number.isFinite(value)) return 3;
  if (metric?.key === "herding") return Math.max(3, Math.min(100, ((value + 1) / 2) * 100));
  return Math.max(3, Math.min(100, value * 100));
}

async function refreshValueScreener() {
  setScreenerScanning(true);
  elements.screenerStatus.textContent = "正在更新最近收盤雷達快照，這次不會逐檔抓日線...";
  showMessage("雷達中心更新中：抓最近收盤快照、股利公告與近年除息資料...");
  try {
    const payload = await postJson("/api/value-screener/refresh", {});
    state.screener = payload;
    renderScreener(payload);
    showMessage(`雷達中心已更新：${formatInteger(payload.summary?.available_rows || 0)} 檔股利資料可用`);
    window.setTimeout(hideMessage, 1800);
  } catch (error) {
    elements.screenerStatus.textContent = `更新失敗：${error.message}`;
    showMessage(error.message, true);
  } finally {
    setScreenerScanning(false);
  }
}

function renderScreener(payload) {
  const summary = payload?.summary || {};
  const priceDate = screenerPriceDate(payload);
  elements.screenerAvailable.textContent = formatInteger(summary.available_rows || 0);
  elements.screenerBelowCheap.textContent = formatInteger(summary.below_cheap_high_conf_rows || summary.below_cheap_rows || 0);
  elements.screenerNearCheap.textContent = formatInteger(summary.gainers_rows || 0);
  elements.screenerComplete.textContent = formatInteger(summary.yield_normal_rows || 0);
  elements.screenerUpdatedAt.textContent = payload?.generated_at
    ? `更新 ${formatDateTime(payload.generated_at)}`
    : "尚未更新";
  if (elements.screenerPriceDate) {
    elements.screenerPriceDate.textContent = priceDate ? `收盤資料 ${priceDate}` : "收盤資料 --";
  }
  elements.screenerStatus.textContent = payload?.generated_at
    ? `雷達快照已更新。排行使用${priceDate ? ` ${priceDate} ` : "最近"}收盤資料；日線、法人與波段關卡仍以「本地資料」下載狀態為準。`
    : "尚未更新。按「更新雷達」只抓 TWSE 最近收盤快照與股利資料；日線、法人請到「本地資料」下載。";

  const highConf = Array.isArray(payload?.below_cheap_high_conf) ? payload.below_cheap_high_conf : [];
  const lowConf = Array.isArray(payload?.below_cheap_low_conf) ? payload.below_cheap_low_conf : [];
  const yieldNormal = Array.isArray(payload?.yield_normal) ? payload.yield_normal : [];
  const yieldTrap = Array.isArray(payload?.yield_trap) ? payload.yield_trap : [];
  const gainers = Array.isArray(payload?.gainers) ? payload.gainers : [];
  const losers = Array.isArray(payload?.losers) ? payload.losers : [];
  const turnoverLeaders = Array.isArray(payload?.turnover_leaders) ? payload.turnover_leaders : [];
  const volumeLeaders = Array.isArray(payload?.volume_leaders) ? payload.volume_leaders : [];
  const amplitudeLeaders = Array.isArray(payload?.amplitude_leaders) ? payload.amplitude_leaders : [];
  const gapUp = Array.isArray(payload?.gap_up) ? payload.gap_up : [];
  const gapDown = Array.isArray(payload?.gap_down) ? payload.gap_down : [];

  // 左欄：資料較完整的股利情境候選
  if (!highConf.length) {
    elements.screenerHighConfList.innerHTML = stateMessageHTML("empty", "尚未更新", "目前沒有資料較完整的股利情境候選。", {
      compact: true,
      className: "screener-empty",
    });
  } else {
    elements.screenerHighConfList.innerHTML = highConf.slice(0, 20).map((item, i) =>
      renderScreenerCheapRow(item, i + 1, "value")
    ).join("");
  }

  // 左欄：低信心折疊
  if (lowConf.length > 0) {
    elements.screenerLowConfCount.textContent = lowConf.length;
    elements.screenerLowConfToggleRow.classList.remove("hidden");
    elements.screenerLowConfList.innerHTML = lowConf.slice(0, 15).map((item) =>
      renderScreenerLowConfRow(item)
    ).join("");
    // 切換顯示/隱藏
    elements.screenerLowConfToggle.onclick = () => {
      const card = elements.screenerLowConfCard;
      const isHidden = card.classList.toggle("hidden");
      elements.screenerLowConfToggle.innerHTML = isHidden
        ? `▾ 另有 <span id="screenerLowConfCount">${lowConf.length}</span> 檔「低信心」已收合　〔顯示〕`
        : `▴ 收合低信心區`;
    };
  } else {
    elements.screenerLowConfToggleRow.classList.add("hidden");
    elements.screenerLowConfCard.classList.add("hidden");
  }

  // 右欄：高殖利率（正常）
  if (!yieldNormal.length) {
    elements.screenerYieldList.innerHTML = stateMessageHTML("empty", "尚未更新", "更新雷達後會顯示高殖利率觀察清單。", {
      compact: true,
      className: "screener-empty",
    });
  } else {
    elements.screenerYieldList.innerHTML = yieldNormal.slice(0, 20).map((item, i) =>
      renderScreenerYieldRow(item, i + 1)
    ).join("");
  }

  // 右欄：疑似陷阱
  if (yieldTrap.length > 0) {
    elements.screenerTrapCard.classList.remove("hidden");
    elements.screenerTrapList.innerHTML = yieldTrap.slice(0, 10).map((item) =>
      renderScreenerTrapRow(item)
    ).join("");
  } else {
    elements.screenerTrapCard.classList.add("hidden");
  }

  // 下方：漲跌榜
  elements.screenerGainersList.innerHTML = gainers.slice(0, 10).map((item, i) =>
    renderScreenerMoverRow(item, i + 1, true)
  ).join("") || stateMessageHTML("empty", "無資料", "目前沒有可顯示的上漲榜資料。", { compact: true, className: "screener-empty" });
  elements.screenerLosersList.innerHTML = losers.slice(0, 10).map((item, i) =>
    renderScreenerMoverRow(item, i + 1, false)
  ).join("") || stateMessageHTML("empty", "無資料", "目前沒有可顯示的下跌榜資料。", { compact: true, className: "screener-empty" });

  const gapLeaders = [
    ...gapUp.slice(0, 5).map((item) => ({ ...item, gap_direction: "up" })),
    ...gapDown.slice(0, 5).map((item) => ({ ...item, gap_direction: "down" })),
  ];
  if (elements.screenerTurnoverList) {
    elements.screenerTurnoverList.innerHTML = turnoverLeaders.slice(0, 10).map((item, i) =>
      renderScreenerSnapshotRow(item, i + 1, "turnover")
    ).join("") || stateMessageHTML("empty", "無資料", "目前沒有成交值資料。", { compact: true, className: "screener-empty" });
  }
  if (elements.screenerVolumeList) {
    elements.screenerVolumeList.innerHTML = volumeLeaders.slice(0, 10).map((item, i) =>
      renderScreenerSnapshotRow(item, i + 1, "volume")
    ).join("") || stateMessageHTML("empty", "無資料", "目前沒有成交量資料。", { compact: true, className: "screener-empty" });
  }
  if (elements.screenerGapList) {
    elements.screenerGapList.innerHTML = gapLeaders.map((item, i) =>
      renderScreenerSnapshotRow(item, i + 1, "gap")
    ).join("") || stateMessageHTML("empty", "無資料", "目前沒有跳空資料。", { compact: true, className: "screener-empty" });
  }
  if (elements.screenerAmplitudeList) {
    elements.screenerAmplitudeList.innerHTML = amplitudeLeaders.slice(0, 10).map((item, i) =>
      renderScreenerSnapshotRow(item, i + 1, "amplitude")
    ).join("") || stateMessageHTML("empty", "無資料", "目前沒有震幅資料。", { compact: true, className: "screener-empty" });
  }
}

function screenerPriceDate(payload) {
  const buckets = [
    payload?.items,
    payload?.gainers,
    payload?.losers,
    payload?.yield_normal,
    payload?.below_cheap_high_conf,
    payload?.below_cheap_low_conf,
  ];
  const dates = new Set();
  buckets.forEach((bucket) => {
    if (!Array.isArray(bucket)) return;
    bucket.forEach((item) => {
      const value = String(item?.price_date || "").trim();
      if (value) dates.add(value);
    });
  });
  const sorted = Array.from(dates).sort();
  if (sorted.length === 0) return "";
  if (sorted.length === 1) return sorted[0];
  return `${sorted[0]} ~ ${sorted[sorted.length - 1]}`;
}

function renderScreenerCheapRow(item, _rank, _mode) {
  const diffPct = item.difference_percent != null
    ? Number(item.difference_percent).toFixed(1) + "%"
    : "--";
  const isBelow = Number(item.difference_percent || 0) <= 0;
  const diffClass = "tone-neutral";
  const diffLabel = isBelow
    ? `相對情境 ${diffPct}`
    : `相對情境 +${diffPct}`;
  return `
    <div class="screener-row screener-row-no-rank" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
      </span>
      <span class="screener-price">收盤 ${formatNumber(item.latest_close)}</span>
      <span class="screener-diff ${diffClass}">${diffLabel}</span>
      ${srBadge(item)}
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function renderScreenerLowConfRow(item) {
  const ctype = item.company_type_label || item.suitability_state || "";
  const reason = item.suitability_reason || "";
  return `
    <div class="screener-row screener-row-no-rank screener-row-dim" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
        ${ctype ? `<span class="screener-ctype">${escapeHtml(ctype)}</span>` : ""}
      </span>
      <span class="screener-dim-reason">${escapeHtml(reason || "低信心")}</span>
      ${srBadge(item)}
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function renderScreenerYieldRow(item, _rank) {
  const yld = item.current_yield_percent != null
    ? Number(item.current_yield_percent).toFixed(1) + "%"
    : "--";
  const years = Number(item.data_years || 0);
  const dataYears = years >= 5 ? "5 年資料完整" : `股利資料 ${formatInteger(years)} 年`;
  const averageCash = item.average_cash_dividend != null
    ? `均息 ${formatNumber(item.average_cash_dividend)}`
    : "均息 --";
  return `
    <div class="screener-row screener-row-no-rank" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
      </span>
      <span class="screener-yield-note-inline">${escapeHtml(dataYears)} · ${escapeHtml(averageCash)}</span>
      <span class="screener-yield-pct tone-up">${yld}</span>
      ${srBadge(item)}
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function renderScreenerTrapRow(item) {
  const yld = item.current_yield_percent != null
    ? Number(item.current_yield_percent).toFixed(1) + "%"
    : "--";
  const trapReason = item.yield_trap_reason === "one_off_dividend"
    ? "含一次性高股利"
    : "需複查";
  return `
    <div class="screener-row screener-row-no-rank screener-row-trap" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
      </span>
      <span class="screener-yield-pct tone-up">${yld}</span>
      <span class="screener-trap-reason">${trapReason}</span>
      ${srBadge(item)}
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function renderScreenerMoverRow(item, rank, isGainer) {
  const pct = item.day_change_percent != null
    ? (isGainer ? "+" : "") + Number(item.day_change_percent).toFixed(2) + "%"
    : "--";
  const cls = isGainer ? "tone-up" : "tone-down";
  return `
    <div class="screener-row" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-rank">${rank}</span>
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
      </span>
      <span class="screener-price">收盤 ${formatNumber(item.latest_close)}</span>
      <span class="${cls} screener-diff">${pct}</span>
      ${srBadge(item)}
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function renderScreenerSnapshotRow(item, rank, type) {
  const metric = screenerSnapshotMetric(item, type);
  return `
    <div class="screener-row" data-screener-stock="${escapeHtml(item.stock_id)}">
      <span class="screener-rank">${rank}</span>
      <span class="screener-name">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || "")}</strong>
        <span class="screener-ctype">收盤 ${formatNumber(item.latest_close)}</span>
      </span>
      <span class="screener-snapshot-metric ${metric.className}">
        <span>${escapeHtml(metric.label)}</span>
        <strong>${escapeHtml(metric.value)}</strong>
      </span>
      <button class="table-action" type="button" data-screener-stock="${escapeHtml(item.stock_id)}">看個股</button>
    </div>
  `;
}

function screenerSnapshotMetric(item, type) {
  if (type === "turnover") {
    return { label: "成交值", value: formatCompactAmount(item.trade_value), className: "tone-neutral" };
  }
  if (type === "volume") {
    return { label: "成交量", value: formatInteger(item.volume), className: "tone-neutral" };
  }
  if (type === "gap") {
    const value = item.opening_gap_percent;
    const direction = item.gap_direction === "down" ? "下跳" : "上跳";
    const className = Number(value) < 0 ? "tone-down" : "tone-up";
    return { label: direction, value: formatSignedPercent(value), className };
  }
  return { label: "震幅", value: formatPlainPercent(item.amplitude_percent), className: "tone-neutral" };
}

async function handleScreenerAction(event) {
  const levelSyncButton = event.target.closest("[data-level-sync-stock]");
  if (levelSyncButton) {
    await syncLevelTarget(levelSyncButton.dataset.levelSyncStock);
    return;
  }

  const button = event.target.closest("[data-screener-stock]");
  if (!button) return;
  await openScreenerStock(button.dataset.screenerStock);
}

async function openScreenerStock(stockId) {
  const target = String(stockId || "").trim();
  if (!target) return;
  await loadStock(target);
}

async function loadStock(stockId, options = {}) {
  const target = String(stockId || "").trim();
  if (!target) return;
  state.activeStockId = target;
  if (!options.quiet) showMessage("讀取本地資料...");
  try {
    const payload = await getJson(`/api/stocks/${encodeURIComponent(target)}?days=365`);
    renderStock(payload, target);
    if (!options.keepSheet) showSheet("stock");
    if (!options.quiet) maybeShowNewbieGuide();
    hideMessage();
    markActiveStock();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function syncStock(stockId, options = {}) {
  const target = String(stockId || "").trim();
  if (!target) return;
  if (state.syncing) return;
  if (!options.force) {
    showMessage(`檢查 ${target} 本地資料日期...`);
    try {
      const freshness = await getJson(`/api/sync/freshness/${encodeURIComponent(target)}`);
      if (freshness?.can_skip_sync) {
        await loadStock(target, { quiet: true });
        showMessage(freshness.message || `${target} 已是最近收盤資料。`);
        window.setTimeout(hideMessage, 1800);
        return;
      }
    } catch (error) {
      showMessage(`無法確認資料日期，改走同步流程：${error.message}`);
    }
  }
  state.syncing = true;
  setSyncing(true);
  state.activeStockId = target;
  renderSyncLoading(target, options);
  showSheet("stock");
  try {
    const payload = await postJson("/api/sync", {
      stock_id: target,
      lookback_days: STOCK_SYNC_LOOKBACK_DAYS,
      skip_if_current: true,
    });
    state.activeStockId = target;
    renderStock(payload, target);
    showSheet("stock");
    maybeShowNewbieGuide();
    elements.searchInput.value = "";
    await loadWatchlist();
    showMessage(payload.sync?.message || "同步完成");
    window.setTimeout(hideMessage, 1800);
  } catch (error) {
    renderSyncFailure(target, error);
    showMessage(error.message, true);
  } finally {
    state.syncing = false;
    setSyncing(false);
    stopSyncProgress();
  }
}

function renderSyncLoading(stockId, options = {}) {
  const label = options.label || stockId;
  state.activePayload = { syncing: true, stock_id: stockId };
  elements.stockMarket.textContent = "TWSE";
  elements.stockTitle.textContent = label;
  elements.stockSubtitle.textContent = "正在建立本地資料，完成後會自動顯示個股頁。";
  elements.stockDataNote.textContent = "第一次同步通常需要較久，視證交所回應速度而定。";
  elements.quoteStatus.textContent = "同步中";
  elements.quotePriceLabel.textContent = "目前價";
  elements.quotePrice.textContent = "--";
  elements.quoteTime.textContent = "同步完成後更新";
  elements.quoteChangeLabel.textContent = "今日漲跌";
  elements.quoteChange.textContent = "--";
  elements.quotePreviousClose.textContent = "--";
  elements.quoteDayRange.textContent = "--";
  elements.quoteOpen.textContent = "--";
  elements.quoteBidAsk.textContent = "--";
  elements.quoteSpread.textContent = "--";
  elements.quoteNote.textContent = "資料下載中，先不要重複點同步。";
  elements.latestClose.textContent = "--";
  elements.dailyChange.textContent = "--";
  elements.pricePosition.textContent = "--";
  elements.rowCount.textContent = "--";
  elements.validationItems.innerHTML = `
    <article class="validation-card neutral">
      <strong>資料同步中</strong>
      <p>系統正在把這檔股票需要的價格、股利與財報資料建立到本地。</p>
    </article>
  `;

  elements.syncProgressPanel.classList.remove("hidden", "sync-progress-error");
  elements.syncProgressTitle.textContent = `正在同步 ${label}`;
  elements.syncProgressDetail.textContent = "請先停在這個畫面，完成或失敗都會在這裡更新。";

  let activeIndex = 0;
  renderSyncSteps(activeIndex);
  stopSyncProgress();
  state.syncStepTimer = window.setInterval(() => {
    activeIndex = Math.min(activeIndex + 1, SYNC_STEPS.length - 1);
    renderSyncSteps(activeIndex);
  }, 2600);
}

function renderSyncFailure(stockId, error) {
  state.activePayload = { sync_error: true, stock_id: stockId };
  elements.stockMarket.textContent = "TWSE";
  elements.stockTitle.textContent = stockId;
  elements.stockSubtitle.textContent = "同步失敗，尚未建立完整個股資料。";
  elements.stockDataNote.textContent = "可以稍後重試；若同一檔一直失敗，再檢查資料源或代號。";
  elements.syncProgressPanel.classList.remove("hidden");
  elements.syncProgressPanel.classList.add("sync-progress-error");
  elements.syncProgressTitle.textContent = `同步 ${stockId} 失敗`;
  elements.syncProgressDetail.textContent = error.message || "資料源暫時沒有回應。";
  elements.syncProgressSteps.innerHTML = `
    <li class="failed">
      <strong>沒有完成同步</strong>
      <span>請按右上角「同步」重試，或換一檔股票確認是否為資料源暫時異常。</span>
    </li>
  `;
}

function renderSyncSteps(activeIndex) {
  elements.syncProgressSteps.innerHTML = SYNC_STEPS.map(([title, detail], index) => {
    const status = index < activeIndex ? "done" : index === activeIndex ? "active" : "pending";
    const label = status === "done" ? "完成" : status === "active" ? "進行中" : "等待";
    return `
      <li class="${status}">
        <strong>${escapeHtml(title)} <em>${label}</em></strong>
        <span>${escapeHtml(detail)}</span>
      </li>
    `;
  }).join("");
}

function hideSyncProgress() {
  stopSyncProgress();
  elements.syncProgressPanel.classList.add("hidden");
  elements.syncProgressPanel.classList.remove("sync-progress-error");
}

function stopSyncProgress() {
  if (!state.syncStepTimer) return;
  window.clearInterval(state.syncStepTimer);
  state.syncStepTimer = null;
}

async function loadPortfolio() {
  try {
    const payload = await getJson("/api/portfolio");
    renderPortfolio(payload);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function savePortfolioTransaction(event) {
  event.preventDefault();
  const transactionId = elements.portfolioTransactionId.value.trim();
  const body = portfolioFormBody();
  elements.portfolioSubmitButton.disabled = true;
  try {
    const payload = transactionId
      ? await putJson(`/api/portfolio/transactions/${encodeURIComponent(transactionId)}`, body)
      : await postJson("/api/portfolio/transactions", body);
    renderPortfolio(payload.portfolio || payload);
    resetPortfolioForm();
    showMessage(transactionId ? "交易已更新" : "交易已儲存");
    window.setTimeout(hideMessage, 1400);
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    elements.portfolioSubmitButton.disabled = false;
  }
}

async function handlePortfolioTableAction(event) {
  const button = event.target.closest("button[data-portfolio-action]");
  if (!button) return;
  const transactionId = Number(button.dataset.transactionId);
  const transaction = (state.portfolio?.transactions || [])
    .find((item) => Number(item.id) === transactionId);
  if (!transaction) return;
  if (button.dataset.portfolioAction === "edit") {
    fillPortfolioForm(transaction);
    return;
  }
  if (!window.confirm("確定刪除這筆交易紀錄？")) return;
  try {
    const payload = await deleteJson(`/api/portfolio/transactions/${encodeURIComponent(transactionId)}`);
    renderPortfolio(payload);
    showMessage("交易已刪除");
    window.setTimeout(hideMessage, 1400);
  } catch (error) {
    showMessage(error.message, true);
  }
}

function exportPortfolioExcel() {
  window.location.href = "/api/export/portfolio.xlsx";
}

function exportStockExcel() {
  if (!state.activeStockId) {
    showMessage("請先開啟一檔股票再匯出。", true);
    return;
  }
  window.location.href = `/api/export/stocks/${encodeURIComponent(state.activeStockId)}.xlsx`;
}

function exportStockReport() {
  if (!state.activeStockId) {
    showMessage("請先開啟一檔股票再匯出。", true);
    return;
  }
  const url = `/api/export/stocks/${encodeURIComponent(state.activeStockId)}.html`;
  const opened = window.open(url, "_blank", "noopener");
  if (!opened) window.location.href = url;
}

function exportScreenerExcel() {
  if (!state.screener?.generated_at) {
    showMessage("請先按「更新雷達」產生資料，再匯出。", true);
    return;
  }
  window.location.href = "/api/export/screener.xlsx";
}

async function loadNews(stockId, name = "") {
  if (!elements.newsList) return;
  if (!stockId) return;
  if (state.newsLoadedFor === stockId) return; // 同一檔已抓過，避免 resize 重複打新聞來源
  state.newsLoadedFor = stockId;
  const requestStockId = stockId;
  elements.newsStatus.textContent = "讀取中…";
  elements.newsOverall.textContent = "正在抓取最近新聞並做關鍵字歸類…";
  elements.newsList.innerHTML = "";
  elements.newsSummaryRiskRadar?.classList.add("hidden");
  elements.newsRiskRadar?.classList.add("hidden");
  setNewsChip("讀取中", "neutral", "正在抓取最近新聞…", []);
  try {
    const query = name ? `?name=${encodeURIComponent(name)}` : "";
    const payload = await getJson(`/api/news/${encodeURIComponent(stockId)}${query}`);
    if (state.activeStockId !== requestStockId) return;
    renderNews(payload);
  } catch (error) {
    state.newsLoadedFor = null; // 失敗就清掉，下次開同檔可重試
    if (state.activeStockId !== requestStockId) return;
    elements.newsStatus.textContent = "暫無法取得";
    elements.newsOverall.textContent = "目前無法取得新聞（可能是沒有網路或來源暫時無回應），稍後再試。";
    elements.newsList.innerHTML = "";
    setNewsChip("暫無法取得", "neutral", "目前無法取得新聞，稍後再試。", []);
  }
}

function setNewsChip(label, tone, text, top) {
  if (!elements.newsChip) return;
  elements.newsChip.textContent = label;
  elements.newsChip.className = `news-chip news-chip-${tone}`;
  if (elements.newsChipText) elements.newsChipText.textContent = text || "";
  if (elements.newsChipTop) {
    elements.newsChipTop.innerHTML = (top || []).map((item) => {
      const t = newsLabelTone(item.label);
      return `<div class="news-chip-line"><span class="news-tag news-tag-${t}">${escapeHtml(item.label || "中性")}</span><span>${escapeHtml(item.title)}</span></div>`;
    }).join("");
  }
}

function newsChipTone(label) {
  if (label === "偏多") return "positive";
  if (label === "偏空") return "caution";
  return "neutral";
}

function renderNews(payload) {
  if (!elements.newsList) return;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const status = payload?.status;
  if (status === "unavailable") {
    elements.newsStatus.textContent = "暫無法取得";
  } else if (!items.length) {
    elements.newsStatus.textContent = "近期無新聞";
  } else {
    const counts = payload.counts || {};
    elements.newsStatus.textContent = `${items.length} 則 · 利多 ${counts["利多"] || 0} / 利空 ${counts["利空"] || 0} / 中性 ${counts["中性"] || 0}`;
  }
  elements.newsOverall.textContent = payload?.overall || "";
  const chipLabel = payload?.overall_label || (items.length ? "中性" : "無消息");
  setNewsChip(chipLabel, newsChipTone(chipLabel), payload?.overall || "", payload?.top || []);
  renderRiskRadar(payload?.risk_summary, elements.newsRiskRadar);
  renderRiskRadar(payload?.risk_summary, elements.newsSummaryRiskRadar);
  state.chartNewsEvents = (items || [])
    .filter((it) => it.risk && Number(it.risk.risk_score || 0) > 0 && /^\d{4}-\d{2}-\d{2}$/.test(String(it.published || "")))
    .map((it) => ({ date: it.published, type: "風險", label: `風險新聞：${it.title}` }));
  if (typeof rebuildEventIndex === "function" && state.chartAll && state.chartAll.length) {
    rebuildEventIndex();
    drawChart();
  }
  state.newsRiskSummary = payload && payload.risk_summary ? payload.risk_summary : null;
  renderAssessmentMerged();
  if (!items.length) {
    elements.newsList.innerHTML = "";
    return;
  }
  const recent = Array.isArray(payload?.recent_events) ? payload.recent_events : [];
  const eventsRow = recent.length
    ? `<div class="news-events-row"><span class="news-events-label">近期動向</span>${recent.map((e) => `<span class="news-event">${escapeHtml(e)}</span>`).join("")}</div>`
    : "";
  elements.newsList.innerHTML = eventsRow + items.map((item) => {
    const tone = newsLabelTone(item.label);
    const link = item.link
      ? `<a class="news-link" href="${escapeHtml(item.link)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>`
      : `<span>${escapeHtml(item.title)}</span>`;
    const meta = [item.source, item.published].filter(Boolean).map(escapeHtml).join(" · ");
    const events = (item.events || []).map((e) => `<span class="news-event">${escapeHtml(e)}</span>`).join("");
    const risk = item.risk || {};
    const hasRisk = Number(risk.risk_score || 0) > 0;
    const riskBadge = hasRisk
      ? `<span class="news-risk-badge risk-${riskItemTone(risk.risk_level)}">地雷 ${escapeHtml(risk.risk_level)} ${escapeHtml(String(risk.risk_score))}</span>`
      : "";
    const riskDetails = hasRisk
      ? `<details class="news-risk-more">
          <summary>風險細節</summary>
          <div class="risk-term-row">${(risk.matched_terms || []).map((t) => `<span class="risk-term">${escapeHtml(t)}</span>`).join("")}</div>
          <div class="risk-dim-row">${Object.entries(risk.dimensions || {}).map(([d, s]) => `<span class="risk-dim">${escapeHtml(d)} ${escapeHtml(String(s))}</span>`).join("")}</div>
        </details>`
      : "";
    return `
      <article class="news-item news-${tone}">
        <span class="news-tag news-tag-${tone}">${escapeHtml(item.label || "中性")}</span>
        <div class="news-body">
          ${link}${riskBadge}
          ${events ? `<div class="news-event-tags">${events}</div>` : ""}
          <div class="news-meta">${meta}${item.reason ? ` · ${escapeHtml(item.reason)}` : ""}</div>
          ${riskDetails}
        </div>
      </article>
    `;
  }).join("");
}

function renderRiskRadar(summary, el = elements.newsRiskRadar) {
  if (!el) return;
  const level = summary?.level;
  if (!summary || !level || level === "無") {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  const tone = riskLevelTone(level);
  const reason = (summary.reasons && summary.reasons.length) ? summary.reasons.join(" ") : "出現需留意的字眼。";
  const heat = summary.heating ? `<span class="risk-heat">風險升溫</span>` : "";
  el.className = `risk-radar risk-${tone}`;
  el.innerHTML = `
    <div class="risk-radar-head">
      <span class="risk-radar-title">地雷雷達</span>
      <span class="risk-level-badge risk-${tone}">${escapeHtml(level)}</span>
      ${heat}
    </div>
    <ol class="risk-reasons">
      <li><strong>消息面</strong>：${escapeHtml(reason)}</li>
      <li><strong>籌碼面</strong>：${escapeHtml(chipsRadarBody(state.activeChips))}</li>
      <li><strong>價量面</strong>：可參考下方走勢圖的 MA5 / MA20 / MA60。</li>
    </ol>
    <p class="disclaimer">地雷雷達只整理新聞中的風險字眼，不預測股價、不構成投資建議。</p>
  `;
}

function riskLevelTone(level) {
  if (level === "警戒") return "high";
  if (level === "注意") return "mid";
  return "low";
}

function riskItemTone(level) {
  if (level === "極高" || level === "高") return "high";
  if (level === "中") return "mid";
  return "low";
}

function newsLabelTone(label) {
  if (label === "利多") return "positive";
  if (label === "利空") return "caution";
  return "neutral";
}

function handlePortfolioStockInput() {
  const query = (elements.portfolioStockId.value || "").trim();
  window.clearTimeout(state.portfolioSearchTimer);
  if (!query) {
    hidePortfolioStockSuggest();
    return;
  }
  state.portfolioSearchTimer = window.setTimeout(() => loadPortfolioStockSuggest(query), 180);
}

async function loadPortfolioStockSuggest(query) {
  if (!elements.portfolioStockSuggest) return;
  try {
    const payload = await getJson(`/api/search?q=${encodeURIComponent(query)}`);
    const results = (payload.results || []).slice(0, 6);
    if (!results.length) {
      hidePortfolioStockSuggest();
      return;
    }
    elements.portfolioStockSuggest.innerHTML = results.map((item) => `
      <button type="button" class="form-suggest-item" data-stock-id="${escapeHtml(item.stock_id)}">
        <strong>${escapeHtml(item.stock_id)} ${escapeHtml(item.short_name || item.name || "")}</strong>
        <span>${item.is_local ? "已下載" : "點選後可同步"}</span>
      </button>
    `).join("");
    elements.portfolioStockSuggest.classList.remove("hidden");
  } catch (error) {
    hidePortfolioStockSuggest();
  }
}

function handlePortfolioStockSuggestPick(event) {
  const button = event.target.closest("[data-stock-id]");
  if (!button) return;
  event.preventDefault(); // mousedown：搶在 input blur 前填值，避免下拉先消失
  elements.portfolioStockId.value = button.dataset.stockId;
  hidePortfolioStockSuggest();
  state.feeManual = false;
  state.taxManual = false;
  autofillTradePrice();
}

function hidePortfolioStockSuggest() {
  elements.portfolioStockSuggest?.classList.add("hidden");
}

async function autofillTradePrice() {
  const stockId = (elements.portfolioStockId.value || "").trim();
  const day = elements.portfolioTradeDate.value;
  if (!elements.portfolioPriceHint) return;
  if (!stockId || !day) return;
  try {
    const payload = await getJson(
      `/api/daily-price?stock_id=${encodeURIComponent(stockId)}&date=${encodeURIComponent(day)}`,
    );
    if (!payload.available) {
      elements.portfolioPriceHint.textContent = payload.message || "查無當日價格，可手動輸入。";
      return;
    }
    const dateNote = payload.is_exact ? payload.date : `${payload.date}（最近交易日）`;
    elements.portfolioPriceHint.textContent =
      `${dateNote}　開 ${formatNumber(payload.open)}／高 ${formatNumber(payload.high)}／低 ${formatNumber(payload.low)}／收 ${formatNumber(payload.close)}`;
    if (!elements.portfolioPrice.value) {
      elements.portfolioPrice.value = payload.close;
      autofillFeeTax();
    }
  } catch (error) {
    elements.portfolioPriceHint.textContent = "";
  }
}

function autofillFeeTax() {
  const shares = Number(elements.portfolioShares.value);
  const price = Number(elements.portfolioPrice.value);
  const amount = shares > 0 && price > 0 ? shares * price : 0;
  if (!amount) return;
  const isEtf = (elements.portfolioStockId.value || "").trim().startsWith("00");
  if (!state.feeManual) {
    elements.portfolioFee.value = Math.max(20, Math.round(amount * 0.001425));
  }
  if (!state.taxManual) {
    const taxRate = isEtf ? 0.001 : 0.003; // ETF 證交稅 0.1%，一般股 0.3%
    elements.portfolioTax.value = elements.portfolioSide.value === "sell" ? Math.round(amount * taxRate) : 0;
  }
}

function portfolioFormBody() {
  return {
    stock_id: elements.portfolioStockId.value.trim(),
    trade_date: elements.portfolioTradeDate.value,
    side: elements.portfolioSide.value,
    shares: Number(elements.portfolioShares.value),
    price: Number(elements.portfolioPrice.value),
    fee: Number(elements.portfolioFee.value || 0),
    tax: Number(elements.portfolioTax.value || 0),
    note: elements.portfolioNote.value.trim(),
  };
}

function renderPortfolio(payload) {
  state.portfolio = payload;
  const summary = payload.summary || {};
  const performance = payload.performance || {};
  const benchmark = performance.benchmark || {};
  const positions = payload.positions || [];
  const transactions = payload.transactions || [];

  elements.portfolioStatus.textContent = `${summary.transactions_count || 0} 筆交易 · ${summary.cost_method || "移動平均成本法"}`;
  elements.portfolioSentence.textContent = summary.sentence || "尚未新增交易。";
  elements.portfolioPositionCount.textContent = `${summary.positions_count || 0}`;
  elements.portfolioCostBasis.textContent = formatMoney(summary.total_cost_basis);
  elements.portfolioMarketValue.textContent = formatMoney(summary.total_market_value);
  elements.portfolioUnrealized.textContent = portfolioPnlText(
    summary.total_unrealized_pnl,
    summary.total_unrealized_return_percent,
  );
  setTone(elements.portfolioUnrealized, summary.total_unrealized_pnl);
  elements.portfolioRealized.textContent = formatSignedMoney(summary.realized_pnl);
  setTone(elements.portfolioRealized, summary.realized_pnl);
  elements.portfolioCashDividends.textContent = formatMoney(performance.total_cash_dividends);
  elements.portfolioTotalReturn.textContent = portfolioPnlText(
    performance.total_return_amount,
    performance.total_return_percent,
  );
  setTone(elements.portfolioTotalReturn, performance.total_return_amount);
  elements.portfolioXirr.textContent = performance.xirr_percent == null
    ? "資料不足"
    : formatPercent(performance.xirr_percent);
  setTone(elements.portfolioXirr, performance.xirr_percent);
  elements.portfolioBenchmark.textContent = benchmark.status === "available"
    ? formatPercent(benchmark.total_return_percent)
    : "待同步";
  setTone(elements.portfolioBenchmark, benchmark.total_return_percent);
  elements.portfolioTransactionCount.textContent = `${transactions.length} 筆`;

  elements.portfolioRows.innerHTML = positions.length
    ? positions.map(renderPortfolioPositionRow).join("")
    : `<tr><td colspan="7">尚無持倉。新增一筆買進交易後，這裡會顯示平均成本與帳面損益。</td></tr>`;

  elements.portfolioTransactionRows.innerHTML = transactions.length
    ? [...transactions].reverse().map(renderPortfolioTransactionRow).join("")
    : `<tr><td colspan="8">尚無交易紀錄。</td></tr>`;

  elements.portfolioLimitations.innerHTML = (payload.limitations || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  elements.portfolioExpertChecks.innerHTML = (payload.expert_checks || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  renderDashboard();
}

function renderDashboard() {
  if (!elements.dashboardSheet) return;
  const portfolio = state.portfolio || {};
  const summary = portfolio.summary || {};
  const positions = portfolio.positions || [];
  const watchlist = state.watchlist || [];
  const totalValue = summary.total_market_value ?? summary.total_cost_basis;
  const pnl = summary.total_unrealized_pnl;
  const returnPercent = summary.total_unrealized_return_percent;

  elements.dashboardGreeting.textContent = dashboardGreetingText();
  elements.dashboardTotalValue.textContent = totalValue == null
    ? "--"
    : `NT$ ${formatMoney(totalValue)}`;
  elements.dashboardReturn.textContent = pnl == null
    ? "尚未有可估算市值的持倉。"
    : `帳面損益 ${formatSignedMoney(pnl)} (${formatPercent(returnPercent)})`;
  elements.dashboardReturn.className = toneClass(pnl);

  elements.dashboardBrief.textContent = buildDashboardBrief(summary, positions, watchlist);
  elements.dashboardAlerts.innerHTML = buildDashboardAlerts(summary, positions, watchlist)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  elements.dashboardHoldings.innerHTML = positions.length
    ? positions.slice(0, 5).map(renderDashboardPosition).join("")
    : stateMessageHTML("empty", "尚未新增交易", "到持倉頁記一筆交易，這裡就會顯示組合摘要。", {
      compact: true,
      className: "dashboard-empty",
    });
  elements.dashboardWatchlist.innerHTML = watchlist.length
    ? watchlist.slice(0, 6).map(renderDashboardWatchlistItem).join("")
    : stateMessageHTML("empty", "尚未加入自選股", "搜尋股票後可以加入觀察。", {
      compact: true,
      className: "dashboard-empty",
    });
}

function dashboardGreetingText() {
  const now = new Date();
  const weekday = ["日", "一", "二", "三", "四", "五", "六"][now.getDay()];
  return `今天是 ${now.getMonth() + 1}/${now.getDate()}（${weekday}），先看這些重點。`;
}

function buildDashboardBrief(summary, positions, watchlist) {
  if ((summary.positions_count || 0) > 0) {
    const leader = positions
      .filter((item) => item.unrealized_pnl != null)
      .sort((a, b) => Number(b.unrealized_pnl) - Number(a.unrealized_pnl))[0];
    const leaderText = leader
      ? `主要變化來自 ${portfolioStockLabel(leader)}。`
      : "部分持股缺少最近收盤價，先補同步資料。";
    return `目前持有 ${summary.positions_count} 檔，帳面損益 ${formatSignedMoney(summary.total_unrealized_pnl)}（${formatPercent(summary.total_unrealized_return_percent)}）。${leaderText}`;
  }
  if (watchlist.length > 0) {
    return `目前有 ${watchlist.length} 檔自選股。可以從自選股挑一檔進個股頁，看白話健檢與估值情境。`;
  }
  return "還沒有持倉或自選股。先搜尋一檔股票，系統會把資料翻成白話。";
}

function buildDashboardAlerts(summary, positions, watchlist) {
  const alerts = [];
  if ((summary.transactions_count || 0) === 0) {
    alerts.push("你還沒有交易紀錄，可以先用持倉頁建立一筆測試資料。");
  }
  const missingPriceCount = summary.missing_price_count || 0;
  if (missingPriceCount > 0) {
    alerts.push(`${missingPriceCount} 檔持股缺少最近收盤價，建議先同步資料。`);
  }
  const concentrated = positions
    .filter((item) => item.market_value != null && summary.total_market_value)
    .map((item) => ({
      label: portfolioStockLabel(item),
      weight: (Number(item.market_value) / Number(summary.total_market_value)) * 100,
    }))
    .sort((a, b) => b.weight - a.weight)[0];
  if (concentrated && concentrated.weight >= 40) {
    alerts.push(`${concentrated.label} 佔比約 ${formatPlainPercent(concentrated.weight)}，集中度偏高。`);
  }
  if (watchlist.length > 0) {
    alerts.push(`自選股 ${watchlist.length} 檔，可從首頁直接進個股分析。`);
  }
  if (alerts.length === 0) {
    alerts.push("目前沒有明顯待辦；可以到個股頁查看估價與事件線索。");
  }
  return alerts.slice(0, 4);
}

function renderDashboardPosition(item) {
  return `
    <button class="dashboard-row" type="button" data-stock-id="${escapeHtml(item.stock_id)}">
      <strong>${escapeHtml(portfolioStockLabel(item))}</strong>
      <span class="${toneClass(item.unrealized_return_percent)}">${formatPercent(item.unrealized_return_percent)}</span>
      <small>${item.latest_close == null ? "缺少收盤價" : `最近收盤 ${formatNumber(item.latest_close)}`}</small>
    </button>
  `;
}

function renderDashboardWatchlistItem(item) {
  const profile = item.profile || { stock_id: item.stock_id, short_name: item.stock_id };
  const latest = item.latest;
  const board = item.board || {};
  const boardLatest = board.latest || {};
  const close = boardLatest.close ?? latest?.close;
  const latestDate = boardLatest.date || latest?.date;
  const changePercent = boardLatest.change_percent;
  const priceText = close == null ? "--" : formatNumber(close);
  const changeText = changePercent == null ? "" : ` ${formatPercent(changePercent)}`;
  return `
    <button class="dashboard-row watchlist-board-row" type="button" data-stock-id="${escapeHtml(profile.stock_id)}">
      <div class="watchlist-board-main">
        <strong>${escapeHtml(profile.stock_id)} ${escapeHtml(profile.short_name || "")}</strong>
        <small>${latestDate ? `資料日 ${escapeHtml(latestDate)}` : "尚無日線資料"}</small>
      </div>
      <span class="watchlist-board-price ${toneClass(changePercent)}">${escapeHtml(priceText)}${escapeHtml(changeText)}</span>
      <div class="watchlist-board-tags">
        ${watchlistBoardTag("體質", board.assessment?.label || "待補", board.assessment?.tone)}
        ${watchlistBoardTag("地雷", board.risk?.label || "待補", board.risk?.tone)}
        ${watchlistBoardTag("關卡", board.level?.status || "待補", board.level?.tone)}
      </div>
    </button>
  `;
}

function watchlistBoardTag(label, value, tone) {
  return `
    <span class="watchlist-board-tag board-tone-${escapeHtml(tone || "unknown")}">
      <em>${escapeHtml(label)}</em>
      <b>${escapeHtml(value || "--")}</b>
    </span>
  `;
}

async function handleDashboardStockClick(event) {
  const button = event.target.closest("[data-stock-id]");
  if (!button) return;
  await loadStock(button.dataset.stockId);
}

function renderPortfolioPositionRow(item) {
  const name = portfolioStockLabel(item);
  const totalMarketValue = Number(state.portfolio?.summary?.total_market_value || 0);
  const allocationPercent = totalMarketValue > 0
    ? (Number(item.market_value || 0) / totalMarketValue) * 100
    : null;
  const allocationWidth = allocationPercent == null
    ? 0
    : Math.max(2, Math.min(100, allocationPercent));
  return `
    <tr>
      <td>${escapeHtml(name)}</td>
      <td>${formatInteger(item.shares)}</td>
      <td>${formatNumber(item.average_cost)}</td>
      <td>${item.latest_close == null ? "--" : `${formatNumber(item.latest_close)}<br><span class="cell-note">${escapeHtml(item.latest_close_date || "")}</span>`}</td>
      <td class="${toneClass(item.unrealized_pnl)}">${formatSignedMoney(item.unrealized_pnl)}</td>
      <td class="${toneClass(item.unrealized_return_percent)}">${formatPercent(item.unrealized_return_percent)}</td>
      <td>
        <div class="portfolio-allocation">
          <span class="allocation-track"><span class="allocation-fill" style="width: ${allocationWidth}%"></span></span>
          <span class="allocation-label">${formatPlainPercent(allocationPercent)}</span>
        </div>
      </td>
    </tr>
  `;
}

function renderPortfolioTransactionRow(item) {
  return `
    <tr>
      <td>${escapeHtml(item.trade_date)}</td>
      <td>${escapeHtml(portfolioStockLabel(item))}</td>
      <td>${sideLabel(item.side)}</td>
      <td>${formatInteger(item.shares)}</td>
      <td>${formatNumber(item.price)}</td>
      <td>${formatMoney((item.fee || 0) + (item.tax || 0))}</td>
      <td>${escapeHtml(item.note || "")}</td>
      <td>
        <button class="table-action" type="button" data-portfolio-action="edit" data-transaction-id="${escapeHtml(item.id)}">編輯</button>
        <button class="table-action danger-text" type="button" data-portfolio-action="delete" data-transaction-id="${escapeHtml(item.id)}">刪除</button>
      </td>
    </tr>
  `;
}

function fillPortfolioForm(transaction) {
  elements.portfolioTransactionId.value = transaction.id || "";
  elements.portfolioStockId.value = transaction.stock_id || "";
  elements.portfolioTradeDate.value = transaction.trade_date || "";
  elements.portfolioSide.value = transaction.side || "buy";
  elements.portfolioShares.value = transaction.shares || "";
  elements.portfolioPrice.value = transaction.price ?? "";
  elements.portfolioFee.value = transaction.fee ?? 0;
  elements.portfolioTax.value = transaction.tax ?? 0;
  elements.portfolioNote.value = transaction.note || "";
  elements.portfolioSubmitButton.textContent = "更新交易";
  elements.portfolioForm.scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetPortfolioForm() {
  elements.portfolioTransactionId.value = "";
  elements.portfolioStockId.value = state.activeStockId || "";
  elements.portfolioTradeDate.value = new Date().toISOString().slice(0, 10);
  elements.portfolioSide.value = "buy";
  elements.portfolioShares.value = "";
  elements.portfolioPrice.value = "";
  elements.portfolioFee.value = "0";
  elements.portfolioTax.value = "0";
  elements.portfolioNote.value = "";
  elements.portfolioSubmitButton.textContent = "儲存交易";
  state.feeManual = false;
  state.taxManual = false;
  if (elements.portfolioPriceHint) elements.portfolioPriceHint.textContent = "";
  hidePortfolioStockSuggest();
}

function portfolioStockLabel(item) {
  const profile = item.profile;
  if (profile?.short_name) return `${item.stock_id} ${profile.short_name}`;
  return item.stock_id;
}

function portfolioPnlText(value, percent) {
  if (value == null) return "--";
  return `${formatSignedMoney(value)} (${formatPercent(percent)})`;
}

function sideLabel(side) {
  return side === "sell" ? "賣出" : "買進";
}

function renderStock(payload, fallbackStockId) {
  const profile = payload.profile;
  const prices = payload.prices || [];
  const summary = payload.summary || {};
  state.activeSummary = summary;
  state.activePayload = payload;
  hideSyncProgress();

  elements.stockMarket.textContent = profile?.market || "TWSE";
  elements.stockTitle.textContent = profile
    ? `${profile.stock_id} ${profile.short_name}`
    : fallbackStockId;
  elements.stockSubtitle.textContent = profile?.name || "本地尚無公司基本資料";
  elements.stockDataNote.textContent = summary.end_date
    ? `資料日 ${summary.end_date}｜日線收盤資料，非即時報價`
    : "日線收盤資料，非即時報價";

  // 公司類型 + 股利法適用性徽章
  const suitability = payload.valuation?.suitability;
  const ctypeBadge = document.querySelector("#stockCtypeBadge");
  const confBadge = document.querySelector("#stockConfBadge");
  if (ctypeBadge) {
    const label = suitability?.company_type_label;
    if (label && suitability?.state !== "applicable") {
      ctypeBadge.textContent = `🏷 ${label}`;
      ctypeBadge.className = "ctype-header-badge";
    } else {
      ctypeBadge.textContent = "";
      ctypeBadge.className = "ctype-header-badge hidden";
    }
  }
  if (confBadge) {
    const suitabilityState = suitability?.state;
    if (suitabilityState && suitabilityState !== "applicable") {
      const tone = suitabilityState === "not_applicable" ? "low" : "medium";
      confBadge.textContent = suitability?.state_label || valuationStateLabel(suitabilityState);
      confBadge.className = `conf-header-badge conf-header-${tone}`;
    } else {
      confBadge.textContent = "";
      confBadge.className = "conf-header-badge hidden";
    }
  }
  if (!elements.portfolioTransactionId.value && !elements.portfolioStockId.value) {
    elements.portfolioStockId.value = profile?.stock_id || fallbackStockId || "";
  }
  elements.latestClose.textContent = formatNumber(summary.latest_close);
  elements.rowCount.textContent = `${summary.rows || 0}`;
  renderPriceWindow(payload.price_window, summary);
  elements.pricePosition.textContent = summary.price_position == null
    ? "--"
    : `${Math.round(summary.price_position * 100)}%`;

  const change = summary.change;
  const changePercent = summary.change_percent;
  elements.dailyChangeLabel.textContent = summary.change_source === "twse_change"
    ? "官方漲跌價差"
    : "較前一交易日";
  elements.dailyChange.classList.toggle("up", change > 0);
  elements.dailyChange.classList.toggle("down", change < 0);
  elements.dailyChange.textContent = change == null
    ? "--"
    : `${change > 0 ? "+" : ""}${formatNumber(change)} (${changePercent > 0 ? "+" : ""}${formatNumber(changePercent)}%)`;

  const latestWithNote = [...prices].reverse().find((item) => item.note);
  elements.latestNote.textContent = summary.change_note || (latestWithNote ? formatPriceNote(latestWithNote.note) : "");
  renderQuote(payload.quote, summary);
  renderStructureCard(payload.structure);
  renderCompanyBrief(payload.brief);
  renderRevenue(payload.revenue_summary, payload.monthly_revenues || []);
  renderFinancial(payload.financial_summary, payload.financial_statements || [], payload.fundamental_trends);
  renderHistoricalFrequency(payload.historical_frequency);
  renderValidation(payload.validation);
  renderHealthReport(payload.report);
  renderValuation(payload.valuation, payload.dividends || [], summary, payload.quote || {});
  renderWatchlistButton(Boolean(payload.is_watchlisted));
  renderRows(prices.filter(isTradingRow));
  state.activeChips = payload.chips || null;
  state.activeAssessment = payload.assessment;
  state.chartNewsEvents = [];
  state.chartPrefs = normalizeChartPrefs(payload.indicator_prefs);
  state.chartAnnotations = Array.isArray(payload.annotations) ? payload.annotations : [];
  setupChart(prices, payload.chips_series || [], buildChartEvents(payload), payload.ma_prices || prices, payload.features || null);
  renderDateEvent((state.chartPrices || []).length - 1);
  renderAnnotationList();
  renderChipsCard(payload.chips);
  renderChartTranslation(payload);
  window.syncChartTourUi?.();
  state.newsRiskSummary = null;
  renderAssessmentMerged();
  scheduleQuoteRefresh();
  loadNews(profile?.stock_id || fallbackStockId, profile?.short_name || profile?.name || "");
}

function renderPriceWindow(priceWindow, summary) {
  const fallbackLabel = summary.start_date && summary.end_date
    ? `${summary.start_date} 至 ${summary.end_date}`
    : "--";
  const isPartial = Boolean(priceWindow?.is_partial || priceWindow?.is_stale);
  elements.priceChartTitle.textContent = isPartial
    ? "可用收盤價（日線，非完整近一年）"
    : "近一年收盤價（日線）";
  elements.dateRange.textContent = priceWindow?.label || fallbackLabel;
  elements.dateRange.classList.toggle("stale", isPartial);
  if (isPartial && priceWindow?.stale_days != null) {
    elements.stockDataNote.textContent += `｜日線資料過期 ${priceWindow.stale_days} 天，請重新同步`;
  }
}

function renderStructureCard(structure) {
  const card = elements.structureCard;
  if (!card) return;
  const dimensions = Array.isArray(structure?.dimensions) ? structure.dimensions : [];
  if (!structure || !dimensions.length) {
    card.hidden = true;
    card.innerHTML = "";
    return;
  }
  card.hidden = false;
  const sufficiency = structure.sufficiency || {};
  const meta = [
    structure.as_of_date ? `資料日 ${escapeHtml(structure.as_of_date)}` : "",
    structure.window ? `${escapeHtml(structure.window)} 日視窗` : "",
    structureSufficiencyLabel(sufficiency.grade),
  ].filter(Boolean).join(" · ");
  const rows = dimensions.map(renderStructureDimension).join("");
  card.innerHTML = `
    <div class="structure-head">
      <div>
        <p class="eyebrow">${escapeHtml(structure.title || "結構指紋")}</p>
        <h3>${escapeHtml(structure.subtitle || "這檔股票現在的性格")}</h3>
        <p>${escapeHtml(meta || "資料充足度待確認")}</p>
      </div>
      <span class="structure-pill">${escapeHtml(structureAvailabilityLabel(structure))}</span>
    </div>
    <div class="structure-grid">${rows}</div>
    <p class="disclaimer">${escapeHtml(structure.disclaimer || "結構描述工具 · 描述現在 · 不預測未來 · 非投資建議")}</p>
  `;
}

function renderStructureDimension(item) {
  const locked = Boolean(item?.locked);
  const grade = locked ? "locked" : (item?.grade || "insufficient");
  const detail = [item?.summary, item?.forbidden, item?.overlap_note].filter(Boolean).join(" ");
  const label = item?.glossary_term
    ? `<button class="term-link" type="button" data-glossary-term="${escapeHtml(item.glossary_term)}">${escapeHtml(item.label || item.key || "--")}</button>`
    : escapeHtml(item?.label || item?.key || "--");
  const valueText = locked
    ? "需市場資料"
    : item?.available
      ? `${Number(item.bar_level ?? 0)} / ${Number(item.bar_max || 5)}`
      : "資料不足";
  return `
    <details class="structure-row structure-grade-${escapeHtml(grade)}" title="${escapeHtml(detail)}">
      <summary>
        <span class="structure-label">${label}</span>
        ${renderStructureBar(item, locked)}
        <span class="structure-value">${escapeHtml(valueText)}</span>
      </summary>
      <div class="structure-detail">
        <p>${escapeHtml(item?.summary || "目前沒有可讀摘要。")}</p>
        <p><strong>不要這樣解讀</strong>：${escapeHtml(item?.forbidden || "不得當成方向或操作訊號。")}</p>
        <p><strong>跟圖上指標差在哪</strong>：${escapeHtml(item?.overlap_note || "這是獨立的結構描述。")}</p>
      </div>
    </details>
  `;
}

function renderStructureBar(item, locked = false) {
  const max = Number(item?.bar_max || 5);
  const level = locked || !item?.available ? 0 : Math.max(0, Math.min(max, Number(item?.bar_level || 0)));
  const cells = Array.from({ length: max }, (_, index) => (
    `<span class="${index < level ? "is-filled" : ""}" aria-hidden="true"></span>`
  )).join("");
  return `<span class="structure-bar" aria-label="${locked ? "鎖定" : `${level} / ${max}`}">${cells}</span>`;
}

function structureSufficiencyLabel(grade) {
  if (grade === "high") return "資料充足";
  if (grade === "medium") return "僅供參考";
  if (grade === "low") return "資料偏少";
  return "資料不足";
}

function structureAvailabilityLabel(structure) {
  if (!structure?.available) return "資料不足";
  return structureSufficiencyLabel(structure?.sufficiency?.grade);
}

async function refreshQuote(stockId) {
  if (!stockId || stockId !== state.activeStockId) return;
  try {
    const payload = await getJson(`/api/quotes/${encodeURIComponent(stockId)}`);
    if (stockId === state.activeStockId) {
      if (state.activePayload) state.activePayload.quote = payload.quote;
      renderQuote(payload.quote, state.activeSummary || {});
    }
  } catch (error) {
    renderQuote(
      {
        available: false,
        status_label: "未取得盤中報價",
        display_price: state.activeSummary?.latest_close,
        display_price_label: "最近收盤",
        message: error.message,
      },
      state.activeSummary || {},
    );
  }
}

function scheduleQuoteRefresh() {
  if (state.quoteTimer) {
    window.clearInterval(state.quoteTimer);
  }
  if (!state.activeStockId) return;
  state.quoteTimer = window.setInterval(() => {
    refreshQuote(state.activeStockId);
  }, 30000);
}

function renderQuote(quote, summary) {
  state.activeQuote = quote || null;
  const fallbackClose = summary?.latest_close;
  const displayPrice = quote?.display_price ?? fallbackClose;
  const displayChange = quote?.display_change;
  const displayChangePercent = quote?.display_change_percent;

  elements.quoteStatus.textContent = quote?.status_label || "未取得盤中報價";
  elements.quotePriceLabel.textContent = quote?.display_price_label || "最近收盤";
  elements.quotePrice.textContent = formatNumber(displayPrice);
  elements.quotePrice.classList.toggle("up", displayChange > 0);
  elements.quotePrice.classList.toggle("down", displayChange < 0);
  elements.quoteTime.textContent = quote?.trade_datetime
    ? `資料時間 ${quote.trade_datetime}`
    : "目前只顯示日線收盤";

  elements.quoteChangeLabel.textContent = quote?.status === "reference_only"
    ? "參考漲跌"
    : "今日漲跌";
  elements.quoteChange.classList.toggle("up", displayChange > 0);
  elements.quoteChange.classList.toggle("down", displayChange < 0);
  elements.quoteChange.textContent = displayChange == null
    ? "--"
    : `${displayChange > 0 ? "+" : ""}${formatNumber(displayChange)} (${displayChangePercent > 0 ? "+" : ""}${formatNumber(displayChangePercent)}%)`;
  elements.quotePreviousClose.textContent = quote?.previous_close == null
    ? "昨收 --"
    : `昨收 ${formatNumber(quote.previous_close)}`;

  elements.quoteDayRange.textContent = quote?.high_price == null || quote?.low_price == null
    ? "--"
    : `${formatNumber(quote.high_price)} / ${formatNumber(quote.low_price)}`;
  elements.quoteOpen.textContent = quote?.open_price == null
    ? "開盤 --"
    : `開盤 ${formatNumber(quote.open_price)}`;

  elements.quoteBidAsk.textContent = quote?.best_bid_price == null || quote?.best_ask_price == null
    ? "--"
    : `${formatNumber(quote.best_bid_price)} / ${formatNumber(quote.best_ask_price)}`;
  elements.quoteSpread.textContent = quote?.spread == null
    ? "價差 --"
    : `價差 ${formatNumber(quote.spread)} (${formatNumber(quote.spread_percent)}%)`;
  elements.quoteNote.textContent = quote?.message || "盤中報價僅供資料檢視，不構成投資建議。";

  // 同步到第一層 hero header 的大字價格
  if (elements.stockHeaderPrice) {
    elements.stockHeaderPrice.textContent = formatNumber(displayPrice);
    elements.stockHeaderPrice.classList.toggle("up", displayChange > 0);
    elements.stockHeaderPrice.classList.toggle("down", displayChange < 0);
  }
  if (elements.stockHeaderPriceLabel) {
    elements.stockHeaderPriceLabel.textContent = quote?.display_price_label || "最近收盤";
  }
  if (elements.stockHeaderChange) {
    elements.stockHeaderChange.textContent = displayChange == null
      ? "--"
      : `${displayChange > 0 ? "+" : ""}${formatNumber(displayChange)} (${displayChangePercent > 0 ? "+" : ""}${formatNumber(displayChangePercent)}%)`;
    elements.stockHeaderChange.classList.toggle("up", displayChange > 0);
    elements.stockHeaderChange.classList.toggle("down", displayChange < 0);
  }
  refreshIntradayChartLayer({
    preserveView: true,
    redraw: Boolean(state.chartLargeMode && state.chartIntradayEnabled),
  });
}

function renderRevenue(summary, records) {
  const latest = records[0];
  elements.revenueStatus.textContent = latest?.source_updated_at
    ? `資料日 ${latest.source_updated_at}`
    : "資料源 TWSE";
  elements.revenueSummaryTitle.textContent = summary?.title || "每月營收待補";
  elements.revenueSummaryValue.textContent = latest
    ? formatRevenue(latest.current_month_revenue)
    : "--";
  elements.revenueSummaryText.textContent = summary?.sentence || "同步後會顯示最新月營收。";
  elements.revenueMom.textContent = formatPercent(latest?.mom_percent);
  elements.revenueYoy.textContent = formatPercent(latest?.yoy_percent);
  elements.revenueCumulativeYoy.textContent = formatPercent(latest?.cumulative_yoy_percent);
  setTone(elements.revenueMom, latest?.mom_percent);
  setTone(elements.revenueYoy, latest?.yoy_percent);
  setTone(elements.revenueCumulativeYoy, latest?.cumulative_yoy_percent);

  elements.revenueRows.innerHTML = records.length
    ? records.map((item) => `
      <tr>
        <td>${escapeHtml(item.year_month)}</td>
        <td>${formatRevenue(item.current_month_revenue)}</td>
        <td class="${toneClass(item.mom_percent)}">${formatPercent(item.mom_percent)}</td>
        <td class="${toneClass(item.yoy_percent)}">${formatPercent(item.yoy_percent)}</td>
        <td>${formatRevenue(item.cumulative_revenue)}</td>
        <td class="${toneClass(item.cumulative_yoy_percent)}">${formatPercent(item.cumulative_yoy_percent)}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="6">尚無每月營收資料，請按同步更新。</td></tr>`;
}

function renderFinancial(summary, records, trends) {
  const latest = records[0];
  elements.financialStatus.textContent = latest?.source_updated_at
    ? `資料日 ${latest.source_updated_at}`
    : "資料源 TWSE";
  elements.financialSummaryTitle.textContent = summary?.title || "獲利資料待補";
  elements.financialSummaryValue.textContent = latest?.eps == null
    ? "--"
    : `${formatNumber(latest.eps)} 元`;
  elements.financialSummaryText.textContent = summary?.sentence || "同步後會顯示 EPS、ROE、ROA。";
  elements.netMargin.textContent = formatPercent(latest?.net_margin_percent);
  elements.roeValue.textContent = formatPercent(latest?.roe_percent);
  elements.roaValue.textContent = formatPercent(latest?.roa_percent);
  setTone(elements.netMargin, latest?.net_margin_percent);
  setTone(elements.roeValue, latest?.roe_percent);
  setTone(elements.roaValue, latest?.roa_percent);

  elements.financialRows.innerHTML = records.length
    ? records.map((item) => `
      <tr>
        <td>${escapeHtml(item.quarter_label)}</td>
        <td>${formatRevenue(item.revenue)}</td>
        <td>${formatPercent(item.gross_margin_percent)}</td>
        <td>${formatPercent(item.operating_margin_percent)}</td>
        <td>${formatRevenue(item.parent_net_income ?? item.net_income)}</td>
        <td>${formatNumber(item.eps)}</td>
        <td>${formatPercent(item.roe_percent)}</td>
        <td>${formatPercent(item.roa_percent)}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="8">尚無最新季財報資料，請按同步更新。</td></tr>`;
  renderFundamentalTrends(trends);
}

function renderFundamentalTrends(trends) {
  if (!elements.fundamentalTrends) return;
  const series = Array.isArray(trends?.series) ? trends.series : [];
  if (!series.length || !trends?.sample_quarters) {
    elements.fundamentalTrends.innerHTML = stateMessageHTML("empty", "多季趨勢待補", "同步多季財報後會顯示毛利率、營益率、淨利率與 ROE。", {
      compact: true,
      className: "fundamental-empty",
    });
    return;
  }
  const sourceDate = trends.source_updated_at ? `資料日 ${trends.source_updated_at}` : `${trends.sample_quarters} 季資料`;
  elements.fundamentalTrends.innerHTML = `
    <div class="fundamental-trends-head">
      <strong>多季基本面趨勢</strong>
      <span>${escapeHtml(sourceDate)}</span>
    </div>
    <div class="fundamental-trend-grid">
      ${series.map(renderFundamentalTrendCard).join("")}
    </div>
    <p class="disclaimer">${escapeHtml(trends.disclaimer || "只呈現已同步財報的歷史百分比，不預測未來。")}</p>
  `;
}

function renderFundamentalTrendCard(item) {
  const points = Array.isArray(item.points) ? item.points : [];
  const latest = item.latest == null ? "--" : formatPlainPercent(item.latest);
  const change = item.change == null ? "前季變動 --" : `前季變動 ${formatSignedPercent(item.change)}`;
  const validPoints = points.filter((point) => Number.isFinite(Number(point.value)));
  const quarterRange = validPoints.length
    ? `${validPoints[0].quarter_label || "--"} → ${validPoints[validPoints.length - 1].quarter_label || "--"}`
    : "資料不足";
  const trendClass = fundamentalTrendClass(item.key);
  return `
    <article class="fundamental-trend-card ${trendClass}">
      <div class="fundamental-trend-card-head">
        <strong>${escapeHtml(item.label || "--")}</strong>
        <span>${escapeHtml(quarterRange)}</span>
      </div>
      <div class="fundamental-trend-value">
        <b>${escapeHtml(latest)}</b>
        <span>${escapeHtml(change)}</span>
      </div>
      ${renderMiniTrendSvg(points, item.label || "")}
    </article>
  `;
}

function renderHistoricalFrequency(report) {
  const el = elements.historicalFrequency;
  if (!el) return;
  if (!report || !report.available) {
    el.innerHTML = stateMessageHTML("empty", "歷史樣本待補", report?.summary || "同步更多日線後會顯示事件後 5/20 日的歷史分布。", {
      compact: true,
      className: "historical-frequency-empty",
    });
    return;
  }
  const events = Array.isArray(report.events) ? report.events : [];
  el.innerHTML = `
    <div class="historical-frequency-head">
      <div>
        <strong>${escapeHtml(report.title || "歷史頻率回測")}</strong>
        <p>${escapeHtml(report.summary || "")}</p>
      </div>
      <span>${escapeHtml(report.start_date || "--")} → ${escapeHtml(report.end_date || "--")}</span>
    </div>
    ${events.length ? `<div class="historical-frequency-grid">${events.map(renderHistoricalFrequencyEvent).join("")}</div>` : stateMessageHTML("empty", "樣本內沒有命中事件", "目前這段資料沒有足夠事件可統計。", { compact: true, className: "historical-frequency-empty" })}
    <p class="historical-frequency-note">${escapeHtml(report.math_note || "")}</p>
    <p class="disclaimer">${escapeHtml(report.disclaimer || "")}</p>
  `;
}

function renderHistoricalFrequencyEvent(event) {
  const windows = Array.isArray(event.windows) ? event.windows : [];
  const current = event.current_match ? `<span class="historical-current">近期出現</span>` : "";
  const currentNote = event.current_match
    ? `<p class="historical-current-note">只表示最近一日也命中此條件，不代表後續走勢。</p>`
    : "";
  const latest = event.latest_trigger_date ? `最近樣本 ${event.latest_trigger_date}` : "樣本內未命中";
  return `
    <article class="historical-event-card">
      <div class="historical-event-head">
        <div>
          <strong>${escapeHtml(event.label || "--")}</strong>
          <p>${escapeHtml(event.description || "")}</p>
        </div>
        ${current}
      </div>
      <div class="historical-event-meta">
        <span>觸發 ${formatInteger(event.trigger_count || 0)} 次</span>
        <span>${escapeHtml(latest)}</span>
      </div>
      ${currentNote}
      <div class="historical-window-grid">
        ${windows.map(renderHistoricalWindow).join("")}
      </div>
    </article>
  `;
}

function renderHistoricalWindow(windowStats) {
  const days = Number(windowStats.days || 0);
  if (!windowStats.available) {
    return `
      <div class="historical-window-card is-empty">
        <strong>${days} 日後</strong>
        <p>完成樣本不足</p>
      </div>
    `;
  }
  const range68 = Array.isArray(windowStats.normal_68_range_percent)
    ? windowStats.normal_68_range_percent.map(formatSignedPercent).join(" ~ ")
    : "--";
  const range95 = Array.isArray(windowStats.normal_95_range_percent)
    ? windowStats.normal_95_range_percent.map(formatSignedPercent).join(" ~ ")
    : "--";
  const hasNormalApproximation = Array.isArray(windowStats.normal_68_range_percent)
    && Array.isArray(windowStats.normal_95_range_percent)
    && Number.isFinite(Number(windowStats.normal_positive_area_percent));
  const quantile = `${formatSignedPercent(windowStats.p25_return_percent)} ~ ${formatSignedPercent(windowStats.p75_return_percent)}`;
  const normalRows = hasNormalApproximation
    ? `
        <div><dt>鐘形假設 68%</dt><dd>${range68}</dd></div>
        <div><dt>鐘形假設 95%</dt><dd>${range95}</dd></div>
        <div><dt>鐘形假設 &gt;0</dt><dd>${formatPlainPercent(windowStats.normal_positive_area_percent)}</dd></div>
      `
    : `<div><dt>鐘形假設</dt><dd>樣本不足不顯示</dd></div>`;
  const notes = [
    windowStats.sample_note || "",
    hasNormalApproximation ? "鐘形假設只做粗略對照，不當成未來機率。" : "",
  ].filter(Boolean).join(" ");
  return `
    <div class="historical-window-card">
      <div class="historical-window-title">
        <strong>${days} 日後</strong>
        <span>${formatInteger(windowStats.count)} 次</span>
      </div>
      <dl>
        <div><dt>正報酬比例</dt><dd>${formatPlainPercent(windowStats.positive_ratio_percent)}</dd></div>
        <div><dt>平均 / 中位</dt><dd>${formatSignedPercent(windowStats.average_return_percent)} / ${formatSignedPercent(windowStats.median_return_percent)}</dd></div>
        <div><dt>中間 50%</dt><dd>${quantile}</dd></div>
        ${normalRows}
      </dl>
      <p>${escapeHtml(notes)}</p>
    </div>
  `;
}

function fundamentalTrendClass(key) {
  return {
    gross_margin_percent: "trend-gross",
    operating_margin_percent: "trend-operating",
    net_margin_percent: "trend-net",
    roe_percent: "trend-roe",
  }[key] || "trend-neutral";
}

function renderMiniTrendSvg(points, label) {
  const valid = (points || [])
    .filter((point) => Number.isFinite(Number(point.value)))
    .map((point) => ({
      quarter: String(point.quarter_label || ""),
      value: Number(point.value),
    }));
  if (valid.length < 2) {
    return `<div class="mini-trend-empty">至少需要 2 季資料</div>`;
  }
  const width = 160;
  const height = 56;
  const padX = 8;
  const padY = 7;
  const values = valid.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = valid.map((point, index) => {
    const x = padX + (index / Math.max(1, valid.length - 1)) * (width - padX * 2);
    const y = height - padY - ((point.value - min) / span) * (height - padY * 2);
    return { ...point, x, y };
  });
  const polyline = coords.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const dots = coords.map((point) => `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="2.4"><title>${escapeHtml(point.quarter)} ${formatPlainPercent(point.value)}</title></circle>`).join("");
  const title = `${label} ${valid[0].quarter} 至 ${valid[valid.length - 1].quarter}`;
  return `
    <svg class="mini-trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
      <line x1="${padX}" y1="${padY}" x2="${padX}" y2="${height - padY}" class="mini-axis"></line>
      <line x1="${padX}" y1="${height - padY}" x2="${width - padX}" y2="${height - padY}" class="mini-axis"></line>
      <polyline points="${polyline}" class="mini-trend-line"></polyline>
      ${dots}
    </svg>
  `;
}

function renderValidation(validation) {
  const items = validation?.items || [];
  const title = document.querySelector("#validationTitle");
  if (title) {
    title.textContent = validation?.title || "明牌驗證工作台";
  }
  elements.validationItems.innerHTML = items.map((item) => `
    <article class="validation-item tone-${escapeHtml(item.tone || "neutral")}">
      <strong>${escapeHtml(item.label)}</strong>
      <p>${renderGlossaryText(item.text)}</p>
    </article>
  `).join("");
}

function renderWatchlistButton(isWatchlisted) {
  elements.watchlistButton.dataset.watchlisted = isWatchlisted ? "true" : "false";
  elements.watchlistButton.innerHTML = `${starIconMarkup()} ${isWatchlisted ? "移除自選" : "加入自選"}`;
  elements.watchlistButton.classList.toggle("danger-button", isWatchlisted);
}

async function toggleWatchlist(stockId) {
  const isWatchlisted = elements.watchlistButton.dataset.watchlisted === "true";
  try {
    if (isWatchlisted) {
      await fetch(`/api/watchlist/${encodeURIComponent(stockId)}`, { method: "DELETE" }).then(readJsonResponse);
      renderWatchlistButton(false);
      showMessage(`${stockId} 已移出自選`);
    } else {
      await postJson("/api/watchlist", { stock_id: stockId });
      renderWatchlistButton(true);
      showMessage(`${stockId} 已加入自選`);
    }
    await loadWatchlist();
    window.setTimeout(hideMessage, 1600);
  } catch (error) {
    showMessage(error.message, true);
  }
}

function renderHealthReport(report) {
  if (!report || !Array.isArray(report.sections)) {
    elements.reportEngine.textContent = "尚無解說";
    elements.healthReport.innerHTML = "";
    elements.reportDisclaimer.textContent = "";
    return;
  }

  elements.reportEngine.textContent = report.engine === "rule_based"
    ? "規則式解說"
    : escapeHtml(report.engine || "解說");
  elements.healthReport.innerHTML = report.sections.map(renderHealthCard).join("");
  elements.reportDisclaimer.textContent = report.disclaimer || "";
}

function renderHealthCard(section) {
  const tone = escapeHtml(section.tone || "neutral");
  const parts = parseHealthSentences(section.sentences || []);
  const hero = parts.hero
    ? `<p class="report-hero">${renderGlossaryText(parts.hero)}</p>`
    : "";
  const stat = parts.stat
    ? `<p class="report-stat">${renderGlossaryText(parts.stat)}</p>`
    : "";
  const extra = parts.extra
    .map((text) => `<p class="report-extra">${renderGlossaryText(text)}</p>`)
    .join("");
  const details = parts.details.length
    ? `<details class="report-more">
        <summary>為什麼 · 要注意</summary>
        <ul>${parts.details.map((line) => `<li>${renderGlossaryText(line)}</li>`).join("")}</ul>
      </details>`
    : "";
  return `
    <article class="report-card tone-${tone}">
      <div class="report-card-head">
        <span class="report-icon">${healthIcon(section.title)}</span>
        <h4>${renderGlossaryText(section.title)}</h4>
        <span class="report-tone">${toneLabel(section.tone)}</span>
      </div>
      ${hero}${stat}${extra}${details}
    </article>
  `;
}

function parseHealthSentences(sentences) {
  const parts = { hero: "", stat: "", details: [], extra: [] };
  for (const sentence of sentences) {
    const [label, body] = splitHealthLabel(sentence);
    if (label === "白話" && !parts.hero) parts.hero = body;
    else if (label === "數字" && !parts.stat) parts.stat = body;
    else if (label === "為什麼" || label === "要注意") parts.details.push(sentence);
    else parts.extra.push(sentence);
  }
  if (!parts.hero) {
    // 沒有「白話：」前綴時，用第一句當結論，其餘進摺疊
    if (parts.extra.length) parts.hero = parts.extra.shift();
    else if (parts.stat) { parts.hero = parts.stat; parts.stat = ""; }
  }
  return parts;
}

function splitHealthLabel(sentence) {
  const text = String(sentence ?? "");
  const index = text.indexOf("：");
  if (index > 0 && index <= 4) {
    return [text.slice(0, index), text.slice(index + 1).trim()];
  }
  return ["", text];
}

function healthIcon(title) {
  const key = String(title || "");
  let path = '<path d="M4 19V5M4 19h16M8 15l3-3 2 2 4-5"/>'; // 趨勢
  if (key.includes("位階")) path = '<path d="M12 3a9 9 0 0 0-9 9h4a5 5 0 0 1 10 0h4a9 9 0 0 0-9-9Z"/><path d="M12 12l4-2"/>';
  else if (key.includes("獲利")) path = '<path d="M4 19V5M4 19h16M8 16v-4M12 16V9M16 16v-7"/>';
  else if (key.includes("波動")) path = '<path d="M3 12c2 0 2-5 4-5s2 10 4 10 2-10 4-10 2 5 4 5"/>';
  else if (key.includes("股利")) path = '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M9.5 9.8c0-1 1.1-1.8 2.5-1.8s2.5.7 2.5 1.6c0 2.2-5 1-5 3.2 0 .9 1.1 1.6 2.5 1.6s2.5-.8 2.5-1.8"/>';
  else if (key.includes("估值") || key.includes("適用")) path = '<path d="M12 3v18M5 8l7-5 7 5M3 12l4-2 4 2-4 2zM13 12l4-2 4 2-4 2z"/>';
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
}

function renderValuationSuitability(suitability) {
  const banner = elements.valuationSuitability;
  const body = elements.valuationDividendBody;
  if (!banner) return;
  if (!suitability) {
    banner.hidden = true;
    banner.innerHTML = "";
    if (body) body.classList.remove("val-collapsed", "val-dim");
    return;
  }
  const state = suitability.state || "applicable";
  const rec = suitability.recommended || {};
  const variant = state === "not_applicable" ? "na" : state === "low_confidence" ? "low" : "ok";
  const tag = suitability.company_type_label
    ? `<span class="ctype-tag">🏷 ${escapeHtml(suitability.company_type_label)}</span>`
    : "";
  const badgeTone = state === "not_applicable" ? "low" : state === "low_confidence" ? "medium" : "high";
  const badge = `<span class="conf-badge conf-${badgeTone}">${escapeHtml(suitability.state_label || valuationStateLabel(state))}</span>`;
  const head = `<div class="sb-head">${tag}${badge}<strong class="sb-title">${escapeHtml(suitability.headline || "")}</strong></div>`;

  banner.hidden = false;
  banner.className = `suitability-banner is-${variant}`;

  if (state === "applicable") {
    banner.innerHTML = head;
    body.classList.remove("val-collapsed", "val-dim");
    return;
  }

  const reasons = (suitability.reason_texts || [])
    .map((text) => `<li>${escapeHtml(text)}</li>`)
    .join("");
  const methods = [];
  if (rec.primary_label && rec.primary && rec.primary !== "yield" && rec.primary !== "none") {
    methods.push(rec.primary_label);
  }
  (rec.secondary_labels || []).forEach((label) => methods.push(label));
  const methodLine = methods.length
    ? `<p class="sb-methods">建議改看 👉 ${methods.map(escapeHtml).join(" · ")}</p>`
    : "";
  const toggle = state === "not_applicable"
    ? `<button type="button" class="sb-toggle" id="valSuitabilityToggle">▸ 仍要看股利法試算（已知參考性低）</button>`
    : "";
  banner.innerHTML = `
    ${head}
    ${reasons ? `<ul class="sb-reasons">${reasons}</ul>` : ""}
    ${methodLine}
    ${toggle}
  `;

  if (state === "not_applicable") {
    body.classList.add("val-collapsed");
    body.classList.remove("val-dim");
    const btn = document.querySelector("#valSuitabilityToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const collapsed = body.classList.toggle("val-collapsed");
        btn.textContent = collapsed
          ? "▸ 仍要看股利法試算（已知參考性低）"
          : "▾ 收起股利法試算";
      });
    }
  } else {
    body.classList.add("val-dim");
    body.classList.remove("val-collapsed");
  }
}

function renderCompanyBrief(brief) {
  if (!elements.companyBriefTitle) return;
  elements.companyBriefTitle.textContent = brief?.company_sentence || "公司資料待補";
  const briefParts = [brief?.valuation_sentence, brief?.beginner_sentence].filter(Boolean);
  const briefText = briefParts.length
    ? briefParts.join(" ")
    : "同步後會顯示這檔股票適合先看哪一把尺。";
  elements.companyBriefText.innerHTML = renderGlossaryText(briefText);
  const watchItems = Array.isArray(brief?.watch_items) ? brief.watch_items : [];
  elements.companyBriefAdvice.textContent = [watchItems[0], brief?.non_advice || "這是資料翻譯，不是買賣建議，也不預測股價。"].filter(Boolean).join(" ");
  const tags = brief?.risk_tags || [];
  elements.companyRiskTags.innerHTML = tags.length
    ? tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
    : `<span>待補風險標籤</span>`;
}

function renderValuation(valuation, dividends, stockSummary = {}, quote = {}) {
  const market = valuation?.market;
  const dividendSummary = valuation?.dividend_summary || {};
  const displayPrice = quote?.display_price ?? stockSummary?.latest_close;
  elements.avgCashDividend.textContent = formatNumber(dividendSummary.average_cash_dividend);
  elements.dividendCoverage.textContent = dividendEstimateLabel(dividendSummary);
  elements.peRatio.textContent = formatNumber(market?.pe_ratio);
  elements.marketDate.textContent = market?.date ? `資料日 ${market.date}` : "尚無官方日資料";
  elements.marketYield.textContent = market?.dividend_yield == null
    ? "--"
    : `${formatNumber(market.dividend_yield)}%`;
  const confidence = valuation?.confidence || "medium";
  renderEtfNote();
  renderValuationSuitability(valuation?.suitability);
  renderValuationBands(valuation?.bands);
  renderRelativeValuation(valuation?.relative, valuation?.vital_signs);
  elements.valuationEstimates.hidden = true;
  elements.valuationEstimates.innerHTML = "";
  if (elements.dividendAssumptionNote) {
    elements.dividendAssumptionNote.textContent = buildDividendAssumptionNote(dividendSummary);
  }
  renderAverageDividendValuation(valuation, displayPrice);
  const suitabilityNotes = valuation?.suitability_notes || [];
  elements.valuationWarning.textContent = [
    valuationConfidenceSentence(confidence),
    ...(suitabilityNotes || []),
    valuation?.warning,
  ].filter(Boolean).join(" ");
  elements.valuationWarning.classList.toggle("caution-note", confidence === "low");
  elements.dividendRows.innerHTML = dividends.length
    ? dividends.map((item) => `
      <tr>
        <td>${escapeHtml(item.year)}</td>
        <td>${escapeHtml(item.period)}</td>
        <td>${formatNumber(item.cash_dividend)}</td>
        <td>${formatNumber(item.stock_dividend)}</td>
        <td>${escapeHtml(item.status)}</td>
      </tr>
    `).join("")
    : `<tr><td colspan="5">尚無股利資料，請先同步或等待資料源補齊。</td></tr>`;
}

function isEtfStock(stockId) {
  const id = String(stockId || "").trim();
  return /^00\d/.test(id) && id.length >= 4; // 台股 ETF 代號 00 開頭（0050/0056/00878…）
}

function renderEtfNote() {
  const note = elements.etfNote;
  if (!note) return;
  if (isEtfStock(state.activeStockId)) {
    note.hidden = false;
    note.innerHTML = `🏷 <strong>ETF</strong> · 一籃子股票，沒有單一公司獲利。下面的「殖利率情境」請當成<strong>配息殖利率區間</strong>參考，<strong>不適用</strong>個股本益比／股利估價。折溢價與成分股集中度待接資料源後再補。`;
  } else {
    note.hidden = true;
    note.innerHTML = "";
  }
}

function renderValuationBands(bands) {
  const container = elements.valuationBands;
  if (!container) return;
  const metrics = [];
  if (bands?.pe?.available) metrics.push(["本益比 (PE)", "pe", bands.pe]);
  if (bands?.pb?.available) metrics.push(["本淨比 (PB)", "pb", bands.pb]);
  if (!metrics.length) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  container.hidden = false;
  container.innerHTML = `
    <div class="bands-head">
      <h4>歷史本益比 / 本淨比河流圖</h4>
      <span class="muted-tag">近 ${escapeHtml(String(bands.years || 5))} 年 · 中性呈現</span>
    </div>
    ${metrics.map(([label, key, band]) => renderRiverBlock(label, key, band)).join("")}
    <p class="disclaimer">${escapeHtml(bands.disclaimer || "只呈現目前倍數在自己近年區間的相對位置，不是估值高低判斷、不預測股價。")}</p>
  `;
  metrics.forEach(([, key, band]) => {
    const canvas = container.querySelector(`#river_${key}`);
    if (canvas) drawValuationRiver(canvas, band);
  });
}

function renderRiverBlock(label, key, band) {
  const pct = band.current_percentile == null ? null : Math.round(Number(band.current_percentile));
  const zone = pct == null ? "資料不足" : pct >= 80 ? "相對高" : pct <= 20 ? "相對低" : "中段";
  const pctText = pct == null ? "" : `近年第 ${pct} 百分位（${zone}）`;
  const hasSeries = Array.isArray(band.series) && band.series.length >= 2;
  const body = hasSeries
    ? `<canvas id="river_${key}" class="band-river" width="600" height="120"></canvas>`
    : renderBandBar(band);
  return `
    <div class="band-row">
      <div class="band-row-head">
        <strong>${escapeHtml(label)}</strong>
        <span>目前 ${formatNumber(band.current)} 倍 · ${pctText}</span>
      </div>
      ${body}
      <div class="band-scale"><span>低 ${formatNumber(band.low)}</span><span>中段帶 = 近年第 20–80 百分位</span><span>高 ${formatNumber(band.high)}</span></div>
    </div>
  `;
}

function renderBandBar(band) {
  const lo = Number(band.low);
  const hi = Number(band.high);
  const span = hi - lo || 1;
  const pos = (v) => Math.max(0, Math.min(100, ((Number(v) - lo) / span) * 100));
  return `
    <div class="band-track">
      <span class="band-zone" style="left:${pos(band.p20)}%; width:${Math.max(0, pos(band.p80) - pos(band.p20))}%"></span>
      <span class="band-tick" style="left:${pos(band.p50)}%"></span>
      <span class="band-cursor" style="left:${pos(band.current)}%"></span>
    </div>
  `;
}

function drawValuationRiver(canvas, band) {
  const series = Array.isArray(band.series) ? band.series : [];
  if (series.length < 2) return;
  const colors = chartThemeColors();
  const values = series.map((p) => Number(p.value));
  const scale = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || canvas.parentElement?.clientWidth || 600;
  const cssHeight = 120;
  canvas.width = Math.floor(cssWidth * scale);
  canvas.height = Math.floor(cssHeight * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const pad = { top: 12, right: 48, bottom: 18, left: 10 };
  const innerW = cssWidth - pad.left - pad.right;
  const innerH = cssHeight - pad.top - pad.bottom;
  const lo = Math.min(Number(band.low), ...values);
  const hi = Math.max(Number(band.high), ...values);
  const range = hi - lo || 1;
  const xAt = (i) => pad.left + (innerW * i) / (series.length - 1);
  const yAt = (v) => pad.top + innerH - ((v - lo) / range) * innerH;

  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = colors.canvasBg;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (band.p20 != null && band.p80 != null) {
    const yTop = yAt(Number(band.p80));
    const yBot = yAt(Number(band.p20));
    ctx.fillStyle = colors.rangeFill;
    ctx.fillRect(pad.left, yTop, innerW, Math.max(1, yBot - yTop));
  }
  if (band.p50 != null) {
    ctx.strokeStyle = colors.muted2;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(pad.left, yAt(Number(band.p50)));
    ctx.lineTo(cssWidth - pad.right, yAt(Number(band.p50)));
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.beginPath();
  series.forEach((point, i) => {
    const px = xAt(i);
    const py = yAt(Number(point.value));
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.strokeStyle = colors.brand;
  ctx.lineWidth = 1.8;
  ctx.stroke();

  const lastIndex = series.length - 1;
  ctx.fillStyle = colors.brand;
  ctx.beginPath();
  ctx.arc(xAt(lastIndex), yAt(values[lastIndex]), 3.5, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = colors.muted2;
  ctx.font = "11px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillText(formatNumber(hi), cssWidth - pad.right + 6, pad.top + 4);
  ctx.fillText(formatNumber(lo), cssWidth - pad.right + 6, cssHeight - pad.bottom);
  ctx.fillText(String(series[0].date || "").slice(0, 7), pad.left, cssHeight - 5);
  const lastLabel = String(series[lastIndex].date || "").slice(0, 7);
  ctx.fillText(lastLabel, cssWidth - pad.right - 38, cssHeight - 5);
}

function renderRelativeValuation(relative, vitalSigns = null) {
  const container = elements.relativeValuation;
  if (!container) return;
  if (relative?.status === "not_applicable") {
    const notes = (relative.notes || [])
      .map((text) => `<li>${escapeHtml(text)}</li>`)
      .join("");
    container.hidden = false;
    container.innerHTML = `
      <article class="relative-card relative-refusal confidence-low">
        <div class="relative-card-head">
          <div>
            <span class="relative-kicker">誠實功能</span>
            <h4>${escapeHtml(relative.headline || "目前先不估價")}</h4>
          </div>
          <span class="conf-badge conf-low">不估價</span>
        </div>
        <p class="relative-headline">這檔現在不適合硬塞股利、PE 或 PB 價格。先看基本面趨勢，等資料穩定再談估值。</p>
        ${notes ? `<ul class="relative-refusal-list">${notes}</ul>` : ""}
        ${renderVitalSigns(vitalSigns)}
      </article>
    `;
    return;
  }
  const methods = (relative?.methods || []).filter((item) => item && item.estimates?.length).slice(0, 2);
  if (!methods.length) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }

  container.hidden = false;
  container.innerHTML = methods.map((method) => {
    const note = (method.notes || [])[0] || method.warning || "";
    const primary = method.method === relative.primary_method;
    const estimates = method.estimates.map((item) => `
      <div class="relative-scenario">
        <span>${escapeHtml(item.label)}</span>
        <strong>${formatApproxPrice(item.price)}</strong>
        <p>${formatNumber(item.multiple)} 倍</p>
      </div>
    `).join("");
    const anchorText = "中心情境等於目前價；上下兩格只看倍數變動敏感度。";
    return `
      <article class="relative-card confidence-${escapeHtml(method.confidence || "medium")} ${primary ? "is-primary" : ""}">
        <div class="relative-card-head">
          <div>
            <span class="relative-kicker">${primary ? "改看主尺" : "輔助尺"}</span>
            <h4>${escapeHtml(method.title)}</h4>
          </div>
          <span class="conf-badge conf-${relativeConfidenceTone(method.confidence)}">${escapeHtml(valuationConfidenceLabel(method.confidence))}</span>
        </div>
        <p class="relative-headline">${escapeHtml(method.headline)}</p>
        <p class="relative-note">以目前倍數為中心；目前倍數本身可能偏高或偏低，這裡不判斷交易基準。</p>
        <div class="relative-metrics">
          <div>
            <span>${escapeHtml(method.basis_label)}</span>
            <strong>${formatNumber(method.basis_value)}</strong>
            <p>${escapeHtml(relativeBasisLabel(method.basis_source))}</p>
          </div>
          <div>
            <span>${escapeHtml(method.multiple_label)}</span>
            <strong>${formatNumber(method.current_multiple)} 倍</strong>
            <p>${escapeHtml(anchorText)}</p>
          </div>
        </div>
        <div class="relative-scenarios">${estimates}</div>
        <p class="relative-note">${escapeHtml(note)}</p>
      </article>
    `;
  }).join("");
}

function renderVitalSigns(vitalSigns) {
  const facts = Array.isArray(vitalSigns?.facts) ? vitalSigns.facts : [];
  if (!facts.length) return "";
  const cards = facts.map((item) => `
    <div class="vital-sign tone-${escapeHtml(item.tone || "neutral")}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <p>${escapeHtml(item.text)}</p>
    </div>
  `).join("");
  return `
    <section class="vital-signs-card tone-${escapeHtml(vitalSigns.tone || "neutral")}">
      <div>
        <span class="relative-kicker">替代看法</span>
        <h5>${escapeHtml(vitalSigns.title || "體質觀察")}</h5>
        <p>${escapeHtml(vitalSigns.sentence || "先看營收、毛利率與 EPS 是否改善。")}</p>
      </div>
      <div class="vital-signs-grid">${cards}</div>
    </section>
  `;
}

function renderAverageDividendValuation(valuation, displayPrice = null) {
  const dividendSummary = valuation?.dividend_summary || {};
  const estimates = valuation?.estimates || [];
  const confidence = valuation?.confidence || "medium";
  if (!estimates.length) {
    elements.historicalYieldStatus.textContent = "資料不足";
    elements.historicalYieldGrid.innerHTML = `
      <div class="estimate-card">
        <span>近 5 年平均股利</span>
        <strong>--</strong>
        <p>需要最近 5 個發放年度股利</p>
      </div>
      <div class="estimate-card">
        <span>高殖利率情境</span>
        <strong>--</strong>
        <p>尚無法反推情境價</p>
      </div>
      <div class="estimate-card">
        <span>平均殖利率情境</span>
        <strong>--</strong>
        <p>尚無歷史平均殖利率</p>
      </div>
      <div class="estimate-card">
        <span>低殖利率情境</span>
        <strong>--</strong>
        <p>尚無歷史低殖利率</p>
      </div>
    `;
    return;
  }

  const estimatesByScenario = new Map(estimates.map((item) => [item.scenario, item]));
  const highYield = estimatesByScenario.get("high_yield");
  const averageYield = estimatesByScenario.get("average_yield");
  const lowYield = estimatesByScenario.get("low_yield");
  const yearsCount = Math.min((dividendSummary.years || []).length, 5);
  elements.historicalYieldStatus.textContent = `${yearsCount || 0} 年資料 · ${valuationConfidenceLabel(confidence)} · 最近 5 個發放年度平均股利`;
  const currentDifference = displayPrice != null && highYield?.price != null
    ? Number(displayPrice) - Number(highYield.price)
    : null;
  const currentDifferencePercent = currentDifference != null && highYield?.price
    ? (currentDifference / Number(highYield.price)) * 100
    : null;
  const differenceText = currentDifference == null
    ? "相對差異 --"
    : `目前價相對此情境 ${formatSignedNumber(currentDifference)} (${formatPercent(currentDifferencePercent)})`;
  elements.historicalYieldGrid.innerHTML = `
    <div class="estimate-card">
      <span>近 5 年平均股利</span>
      <strong>${formatNumber(dividendSummary.average_cash_dividend)}</strong>
      <p>${dividendEstimateLabel(dividendSummary)}</p>
    </div>
    <div class="estimate-card highlight-card confidence-${escapeHtml(confidence)}">
      <span>高殖利率情境</span>
      <strong>${formatApproxPrice(highYield?.price)}</strong>
      <p class="${toneClass(currentDifference)}">${confidence === "low" ? "低信心估算 · " : ""}${differenceText}</p>
    </div>
    <div class="estimate-card">
      <span>平均殖利率情境</span>
      <strong>${formatApproxPrice(averageYield?.price)}</strong>
      <p>用歷史平均殖利率 ${formatNumber(averageYield?.target_yield_percent)}% 反推</p>
    </div>
    <div class="estimate-card">
      <span>低殖利率情境</span>
      <strong>${formatApproxPrice(lowYield?.price)}</strong>
      <p>用歷史低殖利率 ${formatNumber(lowYield?.target_yield_percent)}% 反推</p>
    </div>
  `;
}

function dividendScenarioLabel(item) {
  if (!item) return "股利情境";
  if (item.scenario === "high_yield") return "高殖利率情境";
  if (item.scenario === "average_yield") return "平均殖利率情境";
  if (item.scenario === "low_yield") return "低殖利率情境";
  if (item.target_yield_percent != null) {
    return `要求殖利率 ${formatNumber(item.target_yield_percent)}%`;
  }
  return "股利情境";
}

function buildDividendAssumptionNote(summary = {}) {
  const cash = formatNumber(summary.average_cash_dividend);
  const source = dividendEstimateLabel(summary);
  const stockDividendScope = summary.stock_dividend_scope_note
    ? ` ${summary.stock_dividend_scope_note}`
    : "";
  return `股利情境不是交易基準：它只是在「年股利約 ${cash}、未來配息維持類似水準」的假設下，用要求殖利率反推價格。成長股、循環股、虧損股或配息不穩股票要降權看。資料基礎：${source}。${stockDividendScope}`;
}

function relativeBasisLabel(source) {
  if (source === "latest_four_quarters_eps") return "近四季 EPS 合計";
  if (source === "official_pe_implied_ttm_eps") return "官方 PE 反推";
  if (source === "latest_quarter_eps_annualized") return "最新季 EPS 年化";
  if (source === "latest_financial_book_value") return "最新季財報";
  if (source === "official_pb_implied_book_value") return "官方 PB 反推";
  return "資料來源待確認";
}

function relativeConfidenceTone(confidence) {
  if (confidence === "high") return "high";
  if (confidence === "low") return "low";
  return "medium";
}

function valuationConfidenceLabel(confidence) {
  if (confidence === "high") return "信心較高";
  if (confidence === "low") return "低信心";
  return "信心中等";
}

function valuationConfidenceSentence(confidence) {
  if (confidence === "low") return "這檔不適合只用股利法估價。";
  if (confidence === "high") return "股利樣本較完整，但仍只能當配息回推參考。";
  return "股利樣本尚可，但仍要搭配營收、獲利與產業判讀。";
}

function dividendEstimateLabel(summary) {
  if (summary.estimate_source === "annual_dividend_records") {
    return `${summary.rows} 筆官方股利分派資料`;
  }
  if (summary.estimate_source === "market_yield_implied") {
    return "由官方殖利率與最新收盤反推";
  }
  if (summary.rows) {
    return `${summary.rows} 筆股利資料，尚不足以年化`;
  }
  return "尚無股利資料";
}

function formatPriceNote(note) {
  if (!note) return "";
  if (String(note).includes("change_marker=")) {
    const marker = String(note).split("change_marker=", 2)[1].split(";", 1)[0].trim();
    return `日線含 ${marker || "特殊"} 標記，可能是除權息或特殊交易日；不要用前一天收盤硬減判斷單日漲跌。`;
  }
  return note;
}

function renderRows(prices) {
  const recent = [...prices].slice(-12).reverse();
  elements.priceRows.innerHTML = recent.map((item) => `
    <tr>
      <td>${escapeHtml(item.date)}</td>
      <td>${formatNumber(item.open)}</td>
      <td>${formatNumber(item.high)}</td>
      <td>${formatNumber(item.low)}</td>
      <td>${formatNumber(item.close)}</td>
      <td>${formatInteger(item.volume)}</td>
    </tr>
  `).join("");
}

function renderGlossaryText(text) {
  const source = String(text ?? "");
  if (state.glossary.patterns.length === 0) return escapeHtml(source);

  let html = "";
  let index = 0;
  while (index < source.length) {
    const matched = state.glossary.patterns.find((pattern) => source.startsWith(pattern, index));
    if (matched) {
      const term = state.glossary.aliases.get(matched);
      html += `<button class="term-link" type="button" data-glossary-term="${escapeHtml(term)}">${escapeHtml(matched)}</button>`;
      index += matched.length;
    } else {
      html += escapeHtml(source[index]);
      index += 1;
    }
  }
  return html;
}

function showGlossary(term) {
  const entry = state.glossary.entries.get(term);
  if (!entry) return;
  elements.glossaryTitle.textContent = entry.term;
  elements.glossaryPlain.textContent = entry.plain;
  elements.glossaryHow.textContent = entry.how_to_read;
  if (elements.glossaryGuide) {
    elements.glossaryGuide.innerHTML = entry.reminder ? `<p class="guide-note">${escapeHtml(entry.reminder)}</p>` : "";
    elements.glossaryGuide.classList.toggle("hidden", !entry.reminder);
  }
  elements.glossaryOverlay.classList.remove("hidden");
  elements.glossaryOverlay.setAttribute("aria-hidden", "false");
  elements.glossaryClose.focus();
}

function hideGlossary() {
  elements.glossaryOverlay.classList.add("hidden");
  elements.glossaryOverlay.setAttribute("aria-hidden", "true");
}


function renderDateEvent(index) {
  const payload = state.activePayload || {};
  const prices = state.chartPrices || [];
  if (!prices.length || index == null || index < 0 || index >= prices.length) {
    resetDateEvent();
    return;
  }

  const price = prices[index];
  const previous = index > 0 ? prices[index - 1] : null;
  const changeInfo = dayChangeInfo(price, previous);
  const change = changeInfo.change;
  const changePercent = changeInfo.changePercent;
  const volumeSignal = calculateVolumeSignal(prices, index);
  const localEvents = collectNearbyEvents(payload, price.date);

  elements.eventDate.textContent = price.date;
  elements.eventSummary.textContent = buildDateEventSummary(price, changeInfo, volumeSignal);
  elements.eventClose.textContent = formatNumber(price.close);
  elements.eventDayChange.textContent = change == null
    ? "--"
    : `${change > 0 ? "+" : ""}${formatNumber(change)} (${changePercent > 0 ? "+" : ""}${formatNumber(changePercent)}%)`;
  setTone(elements.eventDayChange, change);
  elements.eventVolume.textContent = formatInteger(price.volume);
  elements.eventVolumeSignal.textContent = volumeSignal.label;
  elements.eventVolumeSignal.className = volumeSignal.tone ? `tone-text-${volumeSignal.tone}` : "";

  elements.eventNewsLink.href = buildNewsSearchUrl(payload.profile, price.date);
  elements.eventNewsLink.textContent = `查 ${price.date} 附近新聞`;
  elements.eventItems.innerHTML = localEvents.length
    ? localEvents.map(renderEventItem).join("")
    : `
      <article class="event-item tone-unknown">
        <strong>本地事件</strong>
        <div>
          <span>${escapeHtml(price.date)}</span>
          <p>附近沒有對到已同步的月營收、財報或股利事件；可以先看價量，再用新聞入口補查外部消息。</p>
        </div>
      </article>
    `;
}

function resetDateEvent() {
  elements.eventDate.textContent = "--";
  elements.eventSummary.textContent = "指到圖表上的日期，這裡會整理當天價格、成交量與附近已知事件。";
  elements.eventClose.textContent = "--";
  elements.eventDayChange.textContent = "--";
  elements.eventDayChange.classList.remove("up", "down");
  elements.eventVolume.textContent = "--";
  elements.eventVolumeSignal.textContent = "--";
  elements.eventVolumeSignal.className = "";
  elements.eventItems.innerHTML = "";
  elements.eventNewsLink.href = "#";
  elements.eventNewsLink.textContent = "查附近新聞";
}

function dayChangeInfo(price, previous) {
  if (price?.change != null) {
    return {
      change: Number(price.change),
      changePercent: previous?.close ? (Number(price.change) / Number(previous.close)) * 100 : null,
      note: formatPriceNote(price.note),
      source: "twse_change",
    };
  }
  const change = previous ? Number(price.close) - Number(previous.close) : null;
  return {
    change,
    changePercent: previous?.close && change != null ? (change / Number(previous.close)) * 100 : null,
    note: "",
    source: "close_to_close",
  };
}

function buildDateEventSummary(price, changeInfo, volumeSignal) {
  const change = changeInfo.change;
  const changePercent = changeInfo.changePercent;
  const prefix = changeInfo.source === "twse_change" ? "官方漲跌價差" : "較前一交易日";
  let changeText = "缺少前一筆交易日，暫時不能比較漲跌";
  if (change != null) {
    if (change > 0) {
      changeText = `${prefix}上漲 ${formatNumber(Math.abs(change))}（${formatPercent(changePercent)}）`;
    } else if (change < 0) {
      changeText = `${prefix}下跌 ${formatNumber(Math.abs(change))}（${formatPercent(changePercent)}）`;
    } else {
      changeText = `${prefix}持平`;
    }
  }
  const noteText = changeInfo.note ? ` ${changeInfo.note}` : "";
  return `這天收盤 ${formatNumber(price.close)}，${changeText}；成交量 ${formatInteger(price.volume)}，${volumeSignal.label}。${noteText}`;
}

function calculateVolumeSignal(prices, index) {
  const currentVolume = Number(prices[index]?.volume);
  const history = prices
    .slice(Math.max(0, index - 20), index)
    .map((item) => Number(item.volume))
    .filter((value) => value > 0);
  if (!currentVolume || history.length < 5) {
    return { label: "量能待比", ratio: null, tone: "unknown" };
  }
  const averageVolume = history.reduce((sum, value) => sum + value, 0) / history.length;
  const ratio = currentVolume / averageVolume;
  if (ratio >= 2) return { label: `爆量 ${formatNumber(ratio)} 倍`, ratio, tone: "caution" };
  if (ratio >= 1.3) return { label: `量放大 ${formatNumber(ratio)} 倍`, ratio, tone: "caution" };
  if (ratio <= 0.6) return { label: `量偏低 ${formatNumber(ratio)} 倍`, ratio, tone: "muted" };
  return { label: "量接近平常", ratio, tone: "neutral" };
}

function collectNearbyEvents(payload, selectedDate) {
  const events = [];
  const addEvent = (event) => {
    const distance = dateDistance(selectedDate, event.eventDate);
    if (distance == null || Math.abs(distance) > 3) return;
    events.push({ ...event, distance });
  };

  (payload.monthly_revenues || []).forEach((item) => {
    addEvent({
      type: "月營收",
      tone: Number(item.yoy_percent) >= 0 ? "positive" : "caution",
      eventDate: item.source_updated_at,
      title: `${item.year_month} 月營收公布`,
      text: `當月營收 ${formatRevenue(item.current_month_revenue)}，年增 ${formatPercent(item.yoy_percent)}，累計年增 ${formatPercent(item.cumulative_yoy_percent)}。`,
    });
  });

  (payload.financial_statements || []).forEach((item) => {
    addEvent({
      type: "財報",
      tone: Number(item.eps) > 0 ? "positive" : "caution",
      eventDate: item.source_updated_at,
      title: `${item.quarter_label} 財報資料`,
      text: `EPS ${formatNumber(item.eps)}，淨利率 ${formatPercent(item.net_margin_percent)}，單季 ROE ${formatPercent(item.roe_percent)}。`,
    });
  });

  (payload.dividends || []).forEach((item) => {
    addEvent({
      type: "股利",
      tone: Number(item.cash_dividend) > 0 || Number(item.stock_dividend) > 0 ? "positive" : "neutral",
      eventDate: item.board_date || item.source_updated_at,
      title: `${item.year} ${item.period} 股利事件`,
      text: `現金股利 ${formatNumber(item.cash_dividend)}，股票股利 ${formatNumber(item.stock_dividend)}，狀態 ${item.status || "未標示"}。`,
    });
  });

  return events
    .sort((a, b) => Math.abs(a.distance) - Math.abs(b.distance))
    .slice(0, 4);
}

function renderEventItem(item) {
  return `
    <article class="event-item tone-${escapeHtml(item.tone || "neutral")}">
      <strong>${escapeHtml(item.type)}</strong>
      <div>
        <span>${escapeHtml(item.eventDate)} · ${escapeHtml(relativeDateLabel(item.distance))}</span>
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(item.text)}</p>
      </div>
    </article>
  `;
}

function relativeDateLabel(distance) {
  if (distance === 0) return "同日";
  if (distance > 0) return `${distance} 天後`;
  return `${Math.abs(distance)} 天前`;
}

function dateDistance(fromDate, toDate) {
  const fromDay = dateToUtcDay(fromDate);
  const toDay = dateToUtcDay(toDate);
  if (fromDay == null || toDay == null) return null;
  return toDay - fromDay;
}

function dateToUtcDay(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const [, year, month, day] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day)) / 86400000;
}

function buildNewsSearchUrl(profile, date) {
  const stockId = profile?.stock_id || state.activeStockId || "";
  const name = profile?.short_name || profile?.name || "";
  const query = `${stockId} ${name} ${date} 股票 新聞`;
  return `https://www.google.com/search?q=${encodeURIComponent(query)}`;
}

const PRICE_MOVING_AVERAGES = [
  { key: "ma5", label: "MA5", window: 5, color: "#8f5f00", width: 1.4 },
  { key: "ma20", label: "月線 MA20", window: 20, color: "#2f63a3", width: 1.5 },
  { key: "ma60", label: "季線 MA60", window: 60, color: "#7a4fb0", width: 1.6 },
];
const CHART_OVERLAY_STYLES = {
  ma5: { color: "#8f5f00", width: 1.4 },
  ma10: { color: "#b26a00", width: 1.2 },
  ma20: { color: "#2f63a3", width: 1.5 },
  ma60: { color: "#7a4fb0", width: 1.6 },
  ma120: { color: "#59656f", width: 1.2 },
  ma240: { color: "#2f7a78", width: 1.2 },
  ema5: { color: "#c47b2a", width: 1 },
  ema12: { color: "#d08c60", width: 1 },
  ema26: { color: "#8b6f47", width: 1 },
  ema50: { color: "#5b8bbd", width: 1.1 },
  ema200: { color: "#46636f", width: 1.1 },
  bb_upper: { color: "#577590", width: 1, dash: [4, 3] },
  bb_middle: { color: "#90a4ae", width: 1, dash: [2, 3] },
  bb_lower: { color: "#577590", width: 1, dash: [4, 3] },
  high_20: { color: "#b0820b", width: 1, dash: [6, 4] },
  low_20: { color: "#1f7a5f", width: 1, dash: [6, 4] },
  high_60: { color: "#8a6d1b", width: 1, dash: [3, 4] },
  low_60: { color: "#2f7a68", width: 1, dash: [3, 4] },
  high_120: { color: "#a15c38", width: 1, dash: [2, 5] },
  low_120: { color: "#307b9d", width: 1, dash: [2, 5] },
  high_250: { color: "#7f5539", width: 1, dash: [8, 5] },
  low_250: { color: "#315b7c", width: 1, dash: [8, 5] },
};
const CHART_SUBPLOT_GROUPS = [
  { key: "rsi", label: "RSI", keys: ["rsi_14", "rsi_6", "rsi_12", "rsi_24"], min: 0, max: 100, color: "#2f63a3" },
  { key: "macd", label: "MACD", keys: ["macd", "macd_signal", "macd_histogram"], color: "#6B4FA0" },
  { key: "kd", label: "KD", keys: ["kd_k", "kd_d", "kd_j"], min: 0, max: 100, color: "#C77D11" },
  { key: "volatility", label: "ATR / HV", keys: ["atr_5", "atr_14", "atr_20", "hv_20", "hv_60", "hv_120"], color: "#B0820B" },
  { key: "obv", label: "OBV", keys: ["obv"], color: "#1C3D5A" },
];
const CHART_VOLUME_MA_KEYS = ["volume_ma5", "volume_ma20", "volume_ma60"];
const CHART_VOLUME_MA_STYLES = {
  volume_ma5: { color: "#8f5f00", width: 1.1 },
  volume_ma20: { color: "#2f63a3", width: 1.2 },
  volume_ma60: { color: "#7a4fb0", width: 1.2 },
};
const CHART_DEFAULT_PREFS = {
  preset: "newbie",
  enabled: ["ma20", "ma60", "volume_ma20", "rsi_14"],
  chart_height: "standard",
  scale: "price",
  ux_mode: "translate",
  experimental_ack: false,
};
const CANDLE_UP_COLOR = "#E03131";   // 台股慣例：收漲為紅
const CANDLE_DOWN_COLOR = "#2F9E44"; // 收跌為綠
const CANDLE_FLAT_COLOR = "#8a96a3";
// 三大法人各自一個色（非紅綠，避免和漲跌混淆）；上=買超、下=賣超
const INST_COLORS = { foreign_net: "#1C3D5A", trust_net: "#C77D11", dealer_net: "#6B4FA0" };
const INST_LABELS = { foreign_net: "外資", trust_net: "投信", dealer_net: "自營商" };
const EVENT_COLORS = { 風險: "#E8590C", 財報: "#2C5475", 營收: "#2C5475", 除息: "#1F9E6B" };

function isTradingRow(p) {
  return Boolean(p) && [p.open, p.high, p.low, p.close].every((v) => Number.isFinite(Number(v)) && Number(v) > 0);
}

function buildIntradayChartRow(quote, officialRows = state.chartOfficialAll || [], officialStockId = state.chartOfficialStockId) {
  if (!quote?.available || quote.current_price == null || !quote.trade_datetime) return null;
  const quoteStockId = String(quote.stock_id || "").trim();
  const expectedStockId = String(officialStockId || state.activeStockId || "").trim();
  if (quoteStockId && expectedStockId && quoteStockId !== expectedStockId) return null;
  const dateText = String(quote.trade_datetime).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText)) return null;
  const lastOfficialDate = officialRows.length ? String(officialRows[officialRows.length - 1]?.date || "") : "";
  if (lastOfficialDate && dateText <= lastOfficialDate) return null;
  const close = Number(quote.current_price);
  const open = Number(quote.open_price ?? quote.previous_close ?? close);
  const rawHigh = Number(quote.high_price ?? close);
  const rawLow = Number(quote.low_price ?? close);
  const high = Math.max(rawHigh, open, close);
  const low = Math.min(rawLow, open, close);
  if (![open, high, low, close].every((value) => Number.isFinite(value) && value > 0)) return null;
  return {
    date: dateText,
    open,
    high,
    low,
    close,
    volume: Number.isFinite(Number(quote.volume)) ? Number(quote.volume) : 0,
    provisional: true,
    source: "TWSE_MIS_INTRADAY",
    note: "盤中暫算，收盤後可能改變。",
  };
}

function refreshIntradayChartLayer(options = {}) {
  const officialRows = Array.isArray(state.chartOfficialAll) ? state.chartOfficialAll : [];
  const officialStockId = String(state.chartOfficialStockId || "").trim();
  const activeStockId = String(state.activeStockId || "").trim();
  if (officialStockId && activeStockId && officialStockId !== activeStockId) {
    state.chartIntradayRow = null;
    updateIntradayChartControls();
    return;
  }
  const previousLength = (state.chartAll || []).length;
  const previousView = state.chartView || { start: 0, end: Math.max(0, previousLength - 1) };
  const wasAtEnd = previousView.end >= Math.max(0, previousLength - 1);
  const intradayRow = state.chartLargeMode && state.chartIntradayEnabled
    ? buildIntradayChartRow(state.activeQuote, officialRows, officialStockId)
    : null;
  state.chartIntradayRow = intradayRow;
  state.chartAll = intradayRow ? [...officialRows, intradayRow] : officialRows;

  const nextLength = state.chartAll.length;
  if (!options.preserveView) {
    state.chartView = { start: 0, end: Math.max(0, nextLength - 1) };
  } else if (state.chartView) {
    const start = Math.max(0, Math.min(state.chartView.start, Math.max(0, nextLength - 1)));
    const end = wasAtEnd ? Math.max(0, nextLength - 1) : Math.max(start, Math.min(state.chartView.end, Math.max(0, nextLength - 1)));
    state.chartView = { start, end };
  }
  rebuildEventIndex();
  updateIntradayChartControls();
  if (options.redraw !== false) drawChart();
}

function isIntradayOverlayActive() {
  return Boolean(state.chartLargeMode && state.chartIntradayEnabled && state.chartIntradayRow);
}

function intradayChartStatusText() {
  const quote = state.activeQuote || {};
  const officialRows = Array.isArray(state.chartOfficialAll) ? state.chartOfficialAll : [];
  const lastOfficialDate = officialRows.length ? String(officialRows[officialRows.length - 1]?.date || "") : "";
  const quoteDate = quote.trade_datetime ? String(quote.trade_datetime).slice(0, 10) : "";
  const quoteStockId = String(quote.stock_id || "").trim();
  const officialStockId = String(state.chartOfficialStockId || "").trim();
  if (quoteStockId && officialStockId && quoteStockId !== officialStockId) return "等待目前股票的盤中報價。";
  if (quoteDate && lastOfficialDate && quoteDate <= lastOfficialDate) return "正式日線已含此日期，不另疊加。";
  if (quote.available && quote.current_price == null) return "目前只有買賣價參考，暫不生成 K 棒。";
  if (!quote.available) return "尚未取得盤中報價，不影響正式日線。";
  return "盤中暫算待成交價，不影響正式日線。";
}

function toggleIntradayChartLayer(force) {
  if (!state.chartLargeMode) return;
  state.chartIntradayEnabled = typeof force === "boolean" ? force : !state.chartIntradayEnabled;
  refreshIntradayChartLayer({ preserveView: true, redraw: true });
}

function updateIntradayChartControls() {
  const btn = elements.chartIntradayBtn;
  const badge = elements.chartIntradayBadge;
  const active = isIntradayOverlayActive();
  if (btn) {
    btn.classList.toggle("is-active", Boolean(state.chartIntradayEnabled));
    btn.textContent = state.chartIntradayEnabled
      ? (active ? "盤中暫算開啟" : "暫算未疊加")
      : "盤中暫算";
    btn.title = "只在大型 K 線圖疊加盤中暫算，不寫入正式日線；收盤後可能改變。";
  }
  if (badge) {
    badge.classList.toggle("hidden", !(state.chartLargeMode && state.chartIntradayEnabled));
    badge.textContent = active
      ? `盤中暫算 ${state.chartIntradayRow.date} ${formatNumber(state.chartIntradayRow.close)} · 收盤後可能改變`
      : intradayChartStatusText();
  }
}

function calculateMovingAverage(prices, windowSize) {
  const result = [];
  const windowValues = [];
  let sum = 0;
  (prices || []).forEach((item) => {
    const value = Number(item && item.close);
    if (!Number.isFinite(value)) { windowValues.length = 0; sum = 0; result.push(null); return; }
    windowValues.push(value); sum += value;
    if (windowValues.length > windowSize) sum -= windowValues.shift();
    result.push(windowValues.length === windowSize ? sum / windowSize : null);
  });
  return result;
}

function computeRangeStats(prices, startIdx, endIdx) {
  const rows = Array.isArray(prices) ? prices : [];
  if (!rows.length) return { available: false, reason: "no_prices" };
  let start = Math.max(0, Math.min(rows.length - 1, Math.trunc(Number(startIdx))));
  let end = Math.max(0, Math.min(rows.length - 1, Math.trunc(Number(endIdx))));
  if (!Number.isFinite(start)) start = 0;
  if (!Number.isFinite(end)) end = rows.length - 1;
  if (start > end) [start, end] = [end, start];
  const selected = rows.slice(start, end + 1);
  if (!selected.length) return { available: false, reason: "empty_range" };
  const numberOf = (item, key) => {
    const value = Number(item && item[key]);
    return Number.isFinite(value) ? value : null;
  };
  const startPrice = numberOf(selected[0], "close");
  const endPrice = numberOf(selected[selected.length - 1], "close");
  const highs = selected.map((item) => numberOf(item, "high")).filter((v) => v != null);
  const lows = selected.map((item) => numberOf(item, "low")).filter((v) => v != null);
  const volumes = selected.map((item) => numberOf(item, "volume")).filter((v) => v != null);
  const closes = selected.map((item) => numberOf(item, "close"));
  const highest = highs.length ? Math.max(...highs) : null;
  const lowest = lows.length ? Math.min(...lows) : null;
  const averageVolume = volumes.length ? volumes.reduce((sum, value) => sum + value, 0) / volumes.length : null;
  const priceChange = startPrice != null && endPrice != null ? endPrice - startPrice : null;
  const priceChangePercent = priceChange != null && startPrice ? (priceChange / startPrice) * 100 : null;
  const amplitudePercent = highest != null && lowest != null && startPrice ? ((highest - lowest) / startPrice) * 100 : null;
  const returns = [];
  for (let i = 1; i < closes.length; i += 1) {
    const prev = closes[i - 1], curr = closes[i];
    if (prev && curr != null) returns.push((curr / prev) - 1);
  }
  const annualizedVolatilityPercent = returns.length >= 2
    ? sampleStdev(returns) * Math.sqrt(252) * 100
    : null;
  return {
    available: true,
    start_index: start,
    end_index: end,
    start_date: selected[0]?.date,
    end_date: selected[selected.length - 1]?.date,
    trading_days: selected.length,
    start_price: startPrice,
    end_price: endPrice,
    price_change: priceChange,
    price_change_percent: priceChangePercent,
    highest,
    lowest,
    amplitude_percent: amplitudePercent,
    average_volume: averageVolume,
    annualized_volatility_percent: annualizedVolatilityPercent,
    vwap: rangeVwap(selected),
  };
}

function sampleStdev(values) {
  if (!Array.isArray(values) || values.length < 2) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function rangeVwap(rows) {
  let tradeValueSum = 0, tradeVolumeSum = 0, hasTradeValue = false;
  let fallbackValueSum = 0, fallbackVolumeSum = 0;
  (rows || []).forEach((item) => {
    const volume = Number(item && item.volume);
    const close = Number(item && item.close);
    const tradeValue = Number(item && item.trade_value);
    if (Number.isFinite(volume) && volume > 0 && Number.isFinite(close)) {
      fallbackValueSum += close * volume;
      fallbackVolumeSum += volume;
    }
    if (Number.isFinite(volume) && volume > 0 && Number.isFinite(tradeValue) && tradeValue > 0) {
      hasTradeValue = true;
      tradeValueSum += tradeValue;
      tradeVolumeSum += volume;
    }
  });
  if (hasTradeValue && tradeVolumeSum) return tradeValueSum / tradeVolumeSum;
  if (fallbackVolumeSum) return fallbackValueSum / fallbackVolumeSum;
  return null;
}

function normalizeChartPrefs(prefs) {
  const merged = { ...CHART_DEFAULT_PREFS, ...(prefs || {}) };
  const enabled = Array.isArray(merged.enabled) ? merged.enabled.map(String) : [...CHART_DEFAULT_PREFS.enabled];
  return {
    preset: String(merged.preset || "newbie"),
    enabled,
    chart_height: ["standard", "tall", "xlarge"].includes(merged.chart_height) ? merged.chart_height : "standard",
    scale: ["price", "log", "percent"].includes(merged.scale) ? merged.scale : "price",
    ux_mode: ["translate", "advanced"].includes(merged.ux_mode) ? merged.ux_mode : "translate",
    experimental_ack: Boolean(merged.experimental_ack),
  };
}

function isChartVisualFeature(feature) {
  return Boolean(feature) && ["overlay", "subplot"].includes(feature.display_type);
}

function chartVisualFeatureKeys() {
  const features = Array.isArray(state.chartCatalog?.features) ? state.chartCatalog.features : [];
  return new Set(features.filter(isChartVisualFeature).map((feature) => feature.key));
}

function applyChartEnabledKeys(keys) {
  const allowed = chartVisualFeatureKeys();
  const source = Array.isArray(keys) ? keys : [];
  state.chartIndicatorEnabled = {};
  source.forEach((key) => {
    const normalized = String(key);
    if (!allowed.size || allowed.has(normalized)) state.chartIndicatorEnabled[normalized] = true;
  });
}

function setupChartPreferences() {
  const prefs = normalizeChartPrefs(state.chartPrefs);
  state.chartPrefs = prefs;
  applyChartEnabledKeys(prefs.enabled || []);
  setChartHeight(prefs.chart_height, { persist: false });
  setChartScale(prefs.scale, { persist: false });
  setChartUxMode(prefs.ux_mode, { persist: false, redraw: false });
}

function setChartHeight(value, options = {}) {
  const height = ["standard", "tall", "xlarge"].includes(value) ? value : "standard";
  state.chartHeight = height;
  if (elements.chartHeightSelect) elements.chartHeightSelect.value = height;
  if (elements.priceChart) {
    elements.priceChart.classList.remove("chart-height-standard", "chart-height-tall", "chart-height-xlarge");
    elements.priceChart.classList.add(`chart-height-${height}`);
  }
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), chart_height: height };
  drawChart();
  if (options.persist) saveChartPrefsSoon();
}

function setChartScale(value, options = {}) {
  const scale = ["price", "log", "percent"].includes(value) ? value : "price";
  state.chartScale = scale;
  if (elements.chartScaleSelect) elements.chartScaleSelect.value = scale;
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), scale };
  drawChart();
  if (options.persist) saveChartPrefsSoon();
}

function setChartUxMode(value, options = {}) {
  const mode = value === "advanced" ? "advanced" : "translate";
  state.chartUxMode = mode;
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), ux_mode: mode };
  const panel = elements.priceChart?.closest(".chart-panel");
  if (panel) {
    panel.classList.toggle("chart-mode-translate", mode === "translate");
    panel.classList.toggle("chart-mode-advanced", mode === "advanced");
  }
  elements.chartModeTranslateBtn?.classList.toggle("is-active", mode === "translate");
  elements.chartModeAdvancedBtn?.classList.toggle("is-active", mode === "advanced");
  if (mode === "advanced") {
    const labPanel = elements.indicatorGroups?.closest(".indicator-panel");
    if (labPanel) labPanel.open = true;
  }
  if (options.redraw !== false) window.setTimeout(drawChart, 40);
  if (options.persist) saveChartPrefsSoon();
}

function saveChartPrefsSoon() {
  window.clearTimeout(state.chartPrefsTimer);
  state.chartPrefsTimer = window.setTimeout(saveChartPrefs, 250);
}

async function saveChartPrefs() {
  try {
    const enabled = Object.entries(state.chartIndicatorEnabled || {})
      .filter(([, value]) => Boolean(value))
      .map(([key]) => key);
    const payload = {
      ...normalizeChartPrefs(state.chartPrefs),
      enabled,
      chart_height: state.chartHeight,
      scale: state.chartScale,
      ux_mode: state.chartUxMode,
    };
    state.chartPrefs = await putJson("/api/indicator-prefs", payload);
  } catch (error) {
    console.warn("indicator prefs save failed", error);
  }
}

function renderIndicatorPanel() {
  const catalog = state.chartCatalog || {};
  const allFeatures = Array.isArray(catalog.features) ? catalog.features : [];
  const features = allFeatures.filter(isChartVisualFeature);
  const categories = Array.isArray(catalog.categories) ? catalog.categories : [];
  const presets = catalog.presets || {};
  const openState = collectIndicatorOpenState();
  if (elements.indicatorPresets) {
    elements.indicatorPresets.innerHTML = Object.entries(presets).map(([key, preset]) => `
      <button type="button" class="indicator-preset ${state.chartPrefs?.preset === key ? "is-active" : ""}" onclick="applyIndicatorPreset('${escapeHtml(key)}')">${escapeHtml(preset.label || key)}</button>
    `).join("");
  }
  if (elements.indicatorGroups) {
    const byCategory = new Map();
    features.forEach((feature) => {
      if (!byCategory.has(feature.category)) byCategory.set(feature.category, []);
      byCategory.get(feature.category).push(feature);
    });
    const visualHtml = categories
      .filter((category) => byCategory.has(category.key))
      .map((category) => {
        const categoryFeatures = byCategory.get(category.key);
        const enabledCount = categoryFeatures.filter((feature) => Boolean(state.chartIndicatorEnabled?.[feature.key])).length;
        const items = categoryFeatures.map((feature) => {
          const checked = Boolean(state.chartIndicatorEnabled?.[feature.key]);
          const risk = Number(feature.risk_level || 1);
          return `
            <label class="indicator-toggle" title="${escapeHtml(feature.description || "")}">
              <input type="checkbox" data-indicator-key="${escapeHtml(feature.key)}" ${checked ? "checked" : ""}>
              <span>${escapeHtml(feature.label || feature.key)}</span>
              ${risk >= 3 ? `<em class="indicator-risk">實驗</em>` : ""}
            </label>
          `;
        }).join("");
        const open = openState.visual.has(category.key)
          ? openState.visual.get(category.key)
          : (["sma", "rsi"].includes(category.key) && enabledCount > 0);
        return `<details class="indicator-group" data-indicator-category="${escapeHtml(category.key)}" ${open ? "open" : ""}><summary>${escapeHtml(category.label || category.key)}<span class="indicator-group-count">${enabledCount}/${categoryFeatures.length}</span></summary><div class="indicator-toggle-list">${items}</div></details>`;
      })
      .join("");
    elements.indicatorGroups.innerHTML = visualHtml + renderIndicatorDataRoom(
      allFeatures.filter((feature) => !isChartVisualFeature(feature)),
      categories,
      openState,
    );
  }
  updateExperimentalNotice();
}

function collectIndicatorOpenState() {
  const visual = new Map();
  const data = new Map();
  elements.indicatorGroups?.querySelectorAll(".indicator-group[data-indicator-category]").forEach((item) => {
    visual.set(item.dataset.indicatorCategory, item.open);
  });
  elements.indicatorGroups?.querySelectorAll(".indicator-data-category[data-indicator-data-category]").forEach((item) => {
    data.set(item.dataset.indicatorDataCategory, item.open);
  });
  const room = elements.indicatorGroups?.querySelector(".indicator-data-room");
  return { visual, data, dataRoomOpen: room ? room.open : false };
}

function renderIndicatorDataRoom(features, categories, openState = null) {
  const items = Array.isArray(features) ? features : [];
  if (!items.length) return "";
  const categoryMeta = Array.isArray(categories) ? categories : [];
  const byCategory = new Map();
  items.forEach((feature) => {
    if (!byCategory.has(feature.category)) byCategory.set(feature.category, []);
    byCategory.get(feature.category).push(feature);
  });
  const categoryHtml = categoryMeta
    .filter((category) => byCategory.has(category.key))
    .map((category) => {
      const rows = byCategory.get(category.key).map((feature) => {
        const value = latestFeatureRawValue(feature.key);
        return `
          <div class="indicator-data-row" title="${escapeHtml(feature.description || "")}">
            <span>${escapeHtml(feature.label || feature.key)}</span>
            <strong>${escapeHtml(formatIndicatorValue(feature.key, value))}</strong>
          </div>
        `;
      }).join("");
      const open = openState?.data?.has(category.key) ? openState.data.get(category.key) : false;
      return `<details class="indicator-data-category" data-indicator-data-category="${escapeHtml(category.key)}" ${open ? "open" : ""}><summary>${escapeHtml(category.label || category.key)}<span class="indicator-group-count">${byCategory.get(category.key).length}</span></summary><div class="indicator-data-list">${rows}</div></details>`;
    })
    .join("");
  return `
    <details class="indicator-data-room" ${openState?.dataRoomOpen ? "open" : ""}>
      <summary>全部數據讀值</summary>
      <div class="indicator-data-room-grid">${categoryHtml}</div>
    </details>
  `;
}

function renderChartTranslation(payload = state.activePayload) {
  if (!elements.chartTranslationPanel) return;
  const assessment = state.activeAssessment || payload?.assessment;
  const available = Boolean(assessment?.available);
  const factors = available ? selectTranslationFactors(assessment.factors || []) : [];
  const weather = chartWeatherFromAssessment(assessment);
  if (elements.chartWeatherBadge) {
    elements.chartWeatherBadge.textContent = weather.label;
    elements.chartWeatherBadge.className = `chart-weather-badge weather-${weather.tone}`;
  }
  if (elements.chartTranslationLine) {
    const details = factors.length
      ? factors.map((factor) => compactFactorReading(factor, 16)).filter(Boolean).join(" · ")
      : "資料還不夠，先同步更多日線再判讀";
    elements.chartTranslationLine.textContent = `${weather.summary} · ${details}`;
  }
  if (elements.chartInsightList) {
    elements.chartInsightList.innerHTML = factors.length
      ? factors.map(renderChartInsightCard).join("")
      : `<article class="chart-insight-card"><strong>資料待補</strong><p>同步更多日線後，這裡只挑三個最值得先看的重點。</p></article>`;
  }
  if (factors[0]) {
    showChartFactorExplanation(factors[0].key, { redraw: false });
  } else {
    renderChartExplainCard({
      title: "大型 K 線圖翻譯機",
      who: "這裡會把圖上的線、指標與當下讀數翻成白話。",
      current: "等待可解讀資料",
      context: "預設只給少量重點；想看全部欄位時再切進進階資料室。",
      caution: "所有判讀只整理歷史資料與傳統解讀，不是預測，也不是買賣建議。",
    });
  }
  renderScenarioRange(payload);
}

function renderChartInsightCard(factor) {
  const title = translationFactorTitle(factor);
  const tone = factorToneClass(factor);
  const reading = compactFactorReading(factor, 48) || factor.lean || "目前沒有明確偏向";
  return `
    <article class="chart-insight-card tone-${escapeHtml(tone)}">
      <strong>${escapeHtml(title)}：${escapeHtml(factor.lean || "觀察")}</strong>
      <p>${escapeHtml(reading)}${factor.value ? `（${escapeHtml(String(factor.value))}）` : ""}</p>
      <button type="button" class="chart-help-btn" aria-label="解釋 ${escapeHtml(title)}" onclick="showChartFactorExplanation('${escapeHtml(factor.key)}')">?</button>
    </article>
  `;
}

function selectTranslationFactors(factors) {
  const source = Array.isArray(factors) ? factors.filter(Boolean) : [];
  const picked = [];
  const used = new Set();
  [["ma"], ["bias", "position"], ["volume"]].forEach((group) => {
    const candidate = source
      .filter((factor) => group.includes(factor.key) && !used.has(factor.key))
      .sort((a, b) => factorImportance(b) - factorImportance(a))[0];
    if (candidate) {
      picked.push(candidate);
      used.add(candidate.key);
    }
  });
  source
    .filter((factor) => !used.has(factor.key))
    .sort((a, b) => factorImportance(b) - factorImportance(a))
    .forEach((factor) => {
      if (picked.length < 3) {
        picked.push(factor);
        used.add(factor.key);
      }
    });
  return picked.slice(0, 3);
}

function factorImportance(factor) {
  const base = {
    ma: 100,
    bias: 92,
    position: 90,
    volume: 86,
    chips: 74,
    valuation: 70,
    fundamental: 68,
    rsi: 60,
    kd: 58,
    news: 56,
  }[factor?.key] || 40;
  const tone = factorToneClass(factor);
  return base + (tone === "neutral" ? 0 : 14);
}

function chartWeatherFromAssessment(assessment) {
  if (!assessment?.available) {
    return { label: "多雲", tone: "cloudy", summary: "資料不足，先不硬判斷" };
  }
  const counts = assessment.counts || recountAssessment(assessment.factors || []);
  const bull = Number(counts.bull || 0);
  const bear = Number(counts.bear || 0);
  if (bull - bear >= 2) return { label: "晴", tone: "sunny", summary: "中期偏多但仍看風險" };
  if (bear - bull >= 2) return { label: "雨", tone: "rainy", summary: "偏弱或風險較多" };
  return { label: "多雲", tone: "cloudy", summary: "多空混合，先看關鍵線" };
}

function translationFactorTitle(factor) {
  return {
    ma: "趨勢",
    bias: "位置",
    position: "位置",
    volume: "量能",
    chips: "籌碼",
    valuation: "估值",
    fundamental: "基本面",
    rsi: "動能",
    kd: "轉折",
    news: "消息",
  }[factor?.key] || (factor?.label || "重點");
}

function compactFactorReading(factor, maxLength = 28) {
  const text = String(factor?.reading || factor?.traditional || factor?.label || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  const first = text.split(/[。；]/)[0] || text;
  return first.length > maxLength ? `${first.slice(0, maxLength)}...` : first;
}

function factorToneClass(factor) {
  return factor?.tone || assessTone(factor?.lean);
}

function showChartFactorExplanation(key, options = {}) {
  const factor = findAssessmentFactor(key);
  if (!factor) return;
  renderChartExplainCard({
    title: factor.label || translationFactorTitle(factor),
    who: `${factor.label || factor.key} 是體質總評裡的一個面向。`,
    current: factor.value ? `${factor.lean || "觀察"}，${factor.value}` : (factor.lean || "觀察"),
    context: factor.reading || "目前沒有更細的白話解讀。",
    caution: factor.traditional || "這只是傳統解讀的清點，不是預測。",
    guideKey: factor.key,
  });
  state.chartFocusedFeature = null;
  if (options.redraw !== false) drawChart();
}

function showChartLayerExplanation(key, options = {}) {
  if (!key) return;
  const feature = chartFeatureSpec(key);
  const factor = findAssessmentFactor(factorKeyForChartFeature(key));
  const latest = latestFeatureRawValue(key);
  renderChartExplainCard({
    title: feature.label || key,
    who: `${feature.label || key}：${feature.description || "圖上的一個資料層。"}`,
    current: formatIndicatorValue(key, latest),
    context: factor?.reading || feature.context_note || feature.description || "這條線只把歷史資料畫出來，需搭配其他面向看。",
    caution: factor?.traditional || feature.caution || "線條穿越與位置只是傳統看法，不代表未來一定照走。",
    guideKey: indicatorGuideKeyForFeature(key),
  });
  state.chartFocusedFeature = key;
  if (options.redraw !== false) drawChart();
}

function showChartCandleExplanation(index) {
  const all = state.chartAll || [];
  const item = all[index] || all[all.length - 1];
  if (!item) return;
  const open = Number(item.open), high = Number(item.high), low = Number(item.low), close = Number(item.close);
  const direction = close > open ? "收漲" : close < open ? "收跌" : "平盤";
  const provisional = Boolean(item.provisional);
  renderChartExplainCard({
    title: `${item.date || "當日"} ${provisional ? "盤中暫算 K 棒" : "K 棒"}`,
    who: "K 棒是一個交易日的開盤、最高、最低、收盤。",
    current: `開 ${formatNumber(open)}、高 ${formatNumber(high)}、低 ${formatNumber(low)}、${provisional ? "暫收" : "收"} ${formatNumber(close)}，${provisional ? "盤中暫算" : direction}`,
    context: "實體表示開盤到收盤的距離，上下影線表示盤中碰過的高低價。",
    caution: provisional ? "這根只用目前盤中報價暫算，收盤後正式日線可能不同。" : "單根 K 棒容易誤讀，通常要搭配趨勢、位置與量能一起看。",
    guideKey: "candle",
  });
  state.chartFocusedFeature = null;
  drawChart();
}

function renderChartExplainCard(detail) {
  const el = elements.chartExplainCard;
  if (!el) return;
  const guide = detail.guideKey && INDICATOR_GUIDES[detail.guideKey]
    ? `<button type="button" class="guide-link" onclick="openIndicatorGuide('${escapeHtml(detail.guideKey)}')">深入名詞小教室</button>`
    : "";
  el.innerHTML = `
    <strong>${escapeHtml(detail.title || "圖表解釋")}</strong>
    <dl>
      <div><dt>我是誰</dt><dd>${escapeHtml(detail.who || "--")}</dd></div>
      <div><dt>現在多少</dt><dd>${escapeHtml(detail.current || "--")}</dd></div>
      <div><dt>對這檔代表什麼</dt><dd>${escapeHtml(detail.context || "--")}</dd></div>
      <div><dt>怎麼看 / 注意</dt><dd>${escapeHtml(detail.caution || "--")}</dd></div>
    </dl>
    ${guide}
  `;
}

function renderScenarioRange(payload = state.activePayload) {
  const panel = elements.scenarioRangePanel;
  if (!panel) return;
  const report = payload?.historical_frequency;
  if (!report?.available) {
    panel.innerHTML = `
      <div class="scenario-head"><strong>歷史情境範圍</strong><span>待補</span></div>
      <p>同步更多日線後，才會顯示類似事件後的歷史分布。</p>
      <div class="scenario-disclaimer">這是歷史統計，不是預測，也不是買賣建議。</div>
    `;
    return;
  }
  const events = Array.isArray(report.events) ? report.events : [];
  const event = pickScenarioEvent(events);
  if (!event) {
    panel.innerHTML = `
      <div class="scenario-head"><strong>歷史情境範圍</strong><span>無命中</span></div>
      <p>目前樣本內沒有可展示的事件分布。</p>
      <div class="scenario-disclaimer">這是歷史統計，不是預測，也不是買賣建議。</div>
    `;
    return;
  }
  const windows = (Array.isArray(event.windows) ? event.windows : [])
    .filter((item) => item?.available)
    .filter((item) => [5, 20].includes(Number(item.days)))
    .slice(0, 2);
  const count = Number(event.completed_sample_count || event.trigger_count || 0);
  panel.innerHTML = `
    <div class="scenario-head">
      <strong>歷史情境（不是預測）</strong>
      <span>${escapeHtml(event.current_match ? "現在剛好符合" : "歷史樣本")}</span>
    </div>
    <p class="scenario-lead">過去這檔出現「${escapeHtml(event.label || "類似型態")}」的情況共 <strong>${formatInteger(count)}</strong> 次。看那之後：</p>
    ${windows.map((windowStats) => renderScenarioWindow(windowStats)).join("")}
    <div class="scenario-disclaimer">這是把過去 ${formatInteger(count)} 次整理出來的範圍，<strong>不是預測、也不是買賣建議</strong>。</div>
  `;
}

function pickScenarioEvent(events) {
  const candidates = (Array.isArray(events) ? events : [])
    .filter((event) => (event.windows || []).some((item) => item?.available));
  return candidates
    .sort((a, b) => {
      if (Boolean(a.current_match) !== Boolean(b.current_match)) return a.current_match ? -1 : 1;
      return Number(b.completed_sample_count || 0) - Number(a.completed_sample_count || 0);
    })[0] || null;
}

function renderScenarioWindow(windowStats) {
  const count = Number(windowStats.count || 0);
  const lo = Number(windowStats.p10_return_percent);
  const hi = Number(windowStats.p90_return_percent);
  const p25 = Number(windowStats.p25_return_percent);
  const p75 = Number(windowStats.p75_return_percent);
  const median = Number(windowStats.median_return_percent);
  const range = Number.isFinite(hi - lo) && hi !== lo ? hi - lo : 1;
  const left = clamp(((p25 - lo) / range) * 100, 0, 100);
  const right = clamp(((p75 - lo) / range) * 100, 0, 100);
  const mid = clamp(((median - lo) / range) * 100, 0, 100);
  const showMedian = count >= 8 && Number.isFinite(median);
  const latestClose = Number(state.activeSummary?.latest_close || (state.chartAll || []).at?.(-1)?.close);
  const priceAt = (pct) => (Number.isFinite(latestClose) && Number.isFinite(pct))
    ? formatNumber(latestClose * (1 + pct / 100))
    : null;
  const goodPx = priceAt(hi);
  const badPx = priceAt(lo);
  const midPx = priceAt(median);
  const days = formatInteger(windowStats.days);
  const rangeText = (badPx && goodPx) ? `${badPx} ~ ${goodPx}` : `${formatSignedPercent(lo)} ~ ${formatSignedPercent(hi)}`;
  const plainRows = [
    showMedian ? `<li><span>最常見</span><b>${midPx ? `約 ${midPx} ` : ""}（${formatSignedPercent(median)}）</b></li>` : "",
    `<li><span>比較好的時候</span><b>${goodPx ? `約 ${goodPx} ` : ""}（${formatSignedPercent(hi)}）</b></li>`,
    `<li><span>比較差的時候</span><b>${badPx ? `約 ${badPx} ` : ""}（${formatSignedPercent(lo)}）</b></li>`,
  ].join("");
  return `
    <div class="scenario-window">
      <div class="scenario-window-head"><span>${days} 天後</span><span>過去 ${formatInteger(count)} 次</span></div>
      <div class="scenario-band" aria-label="${days} 天後歷史範圍">
        <span class="scenario-band-outer"></span>
        <span class="scenario-band-inner" style="left:${left.toFixed(1)}%;right:${(100 - right).toFixed(1)}%"></span>
        ${showMedian ? `<span class="scenario-band-median" style="left:${mid.toFixed(1)}%"></span>` : ""}
      </div>
      <ul class="scenario-plain">${plainRows}</ul>
      <p class="scenario-oneliner">👉 歷史上這種情況，${days} 天後多半落在 <b>${rangeText}</b> 之間${showMedian ? "" : "（樣本少，只看範圍）"}。</p>
      <details class="scenario-advanced"><summary>進階數字</summary><div class="scenario-advanced-body">p10 ${formatSignedPercent(lo)}・p25 ${formatSignedPercent(p25)}・中位 ${formatSignedPercent(median)}・p75 ${formatSignedPercent(p75)}・p90 ${formatSignedPercent(hi)}</div></details>
    </div>
  `;
}

function chartScenarioFanData(payload = state.activePayload) {
  if (isIntradayOverlayActive()) return null;
  const report = payload?.historical_frequency;
  const events = Array.isArray(report?.events) ? report.events : [];
  if (!report?.available || !events.length) return null;
  const event = pickScenarioEvent(events);
  if (!event) return null;
  const windows = (Array.isArray(event.windows) ? event.windows : [])
    .filter((item) => item?.available)
    .filter((item) => [5, 20].includes(Number(item.days)))
    .map((item) => ({
      days: Number(item.days),
      count: Number(item.count || 0),
      p10: Number(item.p10_return_percent),
      p25: Number(item.p25_return_percent),
      median: Number(item.median_return_percent),
      p75: Number(item.p75_return_percent),
      p90: Number(item.p90_return_percent),
    }))
    .filter((item) => [item.p10, item.p25, item.p75, item.p90].every(Number.isFinite))
    .sort((a, b) => a.days - b.days);
  const latestClose = Number(state.activeSummary?.latest_close || (state.chartAll || []).at?.(-1)?.close);
  if (!windows.length || !Number.isFinite(latestClose) || latestClose <= 0) return null;
  return { event, windows, latestClose };
}

function scenarioPriceAtReturn(close, returnPercent) {
  const pct = Number(returnPercent);
  return Number.isFinite(pct) ? close * (1 + pct / 100) : NaN;
}

function findAssessmentFactor(key) {
  if (!key) return null;
  const factors = Array.isArray(state.activeAssessment?.factors) ? state.activeAssessment.factors : [];
  return factors.find((factor) => factor.key === key) || null;
}

function chartFeatureSpec(key) {
  const srLine = findSupportResistanceLine(key);
  if (srLine) {
    return {
      key,
      label: srLine.label,
      description: `${srLine.label} 是近 ${srLine.window} 日波段高低點形成的${srLine.kindLabel}參考線。`,
      context_note: `這條線來自 ${srLine.window} 日範圍內的樞紐 K 棒，用來看股價靠近支撐或壓力的位置。`,
      caution: srLine.provisional
        ? "這是盤中暫算支撐壓力，收盤後正式日線可能改變。"
        : "支撐壓力只是歷史轉折點整理，不代表一定守住或一定突破。",
    };
  }
  const features = Array.isArray(state.chartCatalog?.features) ? state.chartCatalog.features : [];
  const feature = features.find((item) => item.key === key);
  if (feature) return feature;
  if (key === "vol") return { key, label: "成交量", description: "每天市場實際成交的股數，常用來確認價格變動是否有量能支持。" };
  if (String(key).startsWith("sr_")) return { key, label: "支撐 / 壓力", description: "用近期波段高低點畫出的參考區，協助觀察價格靠近哪一側。" };
  if (key === "candle") return { key, label: "K 棒", description: "單日開高低收的價格範圍。" };
  return { key, label: key, description: "圖表資料層。" };
}

function factorKeyForChartFeature(key) {
  const k = String(key || "");
  if (findSupportResistanceLine(k) || k.startsWith("sr_")) return "position";
  if (k === "vol" || k.startsWith("volume") || k === "obv" || k.startsWith("price_up_volume") || k.startsWith("price_down_volume")) return "volume";
  if (/^(ma|ema)\d+/.test(k) || ["bull_alignment", "bear_alignment", "golden_cross", "death_cross", "bb_middle"].includes(k)) return "ma";
  if (k.startsWith("price_to_ma") || k.startsWith("distance_to") || k.startsWith("high_") || k.startsWith("low_") || k.startsWith("bb_")) return "bias";
  if (k.startsWith("rsi")) return "rsi";
  if (k.startsWith("kd")) return "kd";
  if (k.startsWith("trend")) return "ma";
  return null;
}

function indicatorGuideKeyForFeature(key) {
  const factorKey = factorKeyForChartFeature(key);
  if (factorKey && INDICATOR_GUIDES[factorKey]) return factorKey;
  if (String(key).startsWith("sr_")) return "sr";
  if (String(key).startsWith("ma") || String(key).startsWith("ema")) return "ma";
  return null;
}

function latestFeatureRawValue(key) {
  const srLine = findSupportResistanceLine(key);
  if (srLine) return srLine.price;
  if (key === "vol") {
    const latest = (state.chartAll || []).at?.(-1);
    return latest ? latest.volume : null;
  }
  const latest = state.chartFeatures?.latest || {};
  if (Object.prototype.hasOwnProperty.call(latest, key)) return latest[key];
  const values = featureSeries(key);
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] != null) return values[i];
  }
  return null;
}

function formatIndicatorValue(key, value) {
  if (value == null || value === "") return "資料不足";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    if (value.score != null) return `${formatNumber(value.score)} 分`;
    if (value.label) return String(value.label);
    if (value.direction) return String(value.direction);
    return "有資料";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  const k = String(key || "");
  if (k.includes("percent") || k.startsWith("return_") || k.startsWith("roc_") || k.includes("_slope") || k.startsWith("distance_to") || k.startsWith("hv_") || k === "annualized_volatility") {
    return `${formatNumber(number)}%`;
  }
  if (k === "volume_ratio") return `${formatNumber(number)} 倍`;
  if (k.startsWith("volume_ma") || k === "vol" || k === "obv") return formatInteger(Math.round(number));
  return formatNumber(number);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function applyIndicatorPreset(key) {
  const catalog = state.chartCatalog || {};
  const preset = (catalog.presets || {})[key];
  if (!preset) return;
  applyChartEnabledKeys(preset.enabled || []);
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), preset: key };
  renderIndicatorPanel();
  updateChartLegendState();
  drawChart();
  saveChartPrefsSoon();
}

function handleIndicatorToggleChange(event) {
  const input = event.target.closest?.("[data-indicator-key]");
  if (!input) return;
  const key = input.dataset.indicatorKey;
  state.chartIndicatorEnabled[key] = Boolean(input.checked);
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), preset: "custom" };
  renderIndicatorPanel();
  updateChartLegendState();
  if (state.chartLargeMode) showChartLayerExplanation(key, { redraw: false });
  drawChart();
  saveChartPrefsSoon();
}

function indicatorEnabled(key) {
  if (!key) return false;
  if (state.chartLargeMode && chartVisualFeatureKeys().has(key)) {
    return Boolean(state.chartIndicatorEnabled?.[key]);
  }
  if (state.chartIndicatorEnabled && Object.prototype.hasOwnProperty.call(state.chartIndicatorEnabled, key)) {
    return Boolean(state.chartIndicatorEnabled[key]);
  }
  const hidden = state.chartSeriesHidden || {};
  return !hidden[key];
}

function updateExperimentalNotice() {
  if (!elements.experimentalNotice) return;
  const features = (Array.isArray(state.chartCatalog?.features) ? state.chartCatalog.features : []).filter(isChartVisualFeature);
  const hasExperimental = features.some((feature) => Number(feature.risk_level || 1) >= 3 && indicatorEnabled(feature.key));
  elements.experimentalNotice.classList.toggle("hidden", !hasExperimental || Boolean(state.chartPrefs?.experimental_ack));
}

function ackExperimentalIndicators() {
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), experimental_ack: true };
  updateExperimentalNotice();
  saveChartPrefsSoon();
}

function featureSeries(key) {
  const values = state.chartFeatures?.series?.[key];
  return Array.isArray(values) ? values : [];
}

function buildOverlaySeries(valid, maSource) {
  const catalog = state.chartCatalog || {};
  const features = Array.isArray(catalog.features) ? catalog.features : [];
  const overlayFeatures = features.filter((feature) => feature.display_type === "overlay" && featureSeries(feature.key).length);
  if (overlayFeatures.length) {
    return overlayFeatures.map((feature) => ({
      key: feature.key,
      label: feature.label || feature.key,
      values: featureSeries(feature.key),
      ...(CHART_OVERLAY_STYLES[feature.key] || { color: "#64748B", width: 1 }),
    }));
  }
  return PRICE_MOVING_AVERAGES.map((s) => ({
    ...s,
    values: calculateAlignedMovingAverage(valid, maSource, s.window),
  }));
}

// ---- 設定整合圖（價格 + 三大法人 + 事件），預設顯示全部，可滾輪縮放、拖曳平移 ----
function setupChart(prices, chipsSeries, localEvents, maPrices = null, features = null) {
  const valid = (prices || []).filter(isTradingRow);
  const maSource = (maPrices || prices || []).filter(isTradingRow);
  if (!state.chartSeriesHidden) state.chartSeriesHidden = { vol: true, sr_s: true, sr_l: true };
  state.chartFeatures = features || null;
  state.chartCatalog = features?.catalog || state.chartCatalog || null;
  setupChartPreferences();
  state.chartOfficialAll = valid;
  state.chartOfficialStockId = state.activePayload?.profile?.stock_id || state.activeStockId || null;
  state.chartAll = valid;
  state.chartPrices = valid; // 與 renderDateEvent 等相容
  const chipsMap = {};
  (chipsSeries || []).forEach((c) => { if (c && c.date) chipsMap[c.date] = c; });
  state.chartChips = chipsMap;
  state.chartClassicMA = PRICE_MOVING_AVERAGES.map((s) => ({
    ...s,
    values: calculateAlignedMovingAverage(valid, maSource, s.window),
  }));
  state.chartMA = buildOverlaySeries(valid, maSource);
  state.chartLocalEvents = localEvents || [];
  state.chartNewsEvents = state.chartNewsEvents || [];
  rebuildEventIndex();
  const n = valid.length;
  state.chartView = { start: 0, end: Math.max(0, n - 1) };
  state.chartHoverIndex = null;
  state.chartHoverFeatureKey = null;
  state.chartHoverFeatureIndex = null;
  state.chartHoverPoint = null;
  state.chartFocusedFeature = null;
  state.chartDragging = false;
  state.chartSelectingRange = false;
  state.chartRangeSelection = null;
  state.chartRangeDraft = null;
  refreshIntradayChartLayer({ preserveView: false, redraw: false });
  drawChart();
  renderIndicatorPanel();
  renderAnnotationList();
  renderRangeStatsPanel();
  updateChartLegendState();
}

function calculateAlignedMovingAverage(visiblePrices, sourcePrices, windowSize) {
  const visible = Array.isArray(visiblePrices) ? visiblePrices : [];
  const source = Array.isArray(sourcePrices) && sourcePrices.length ? sourcePrices : visible;
  if (!visible.length) return [];
  const sourceValues = calculateMovingAverage(source, windowSize);
  let offset = source.findIndex((item) => item?.date && item.date === visible[0]?.date);
  if (offset < 0) offset = Math.max(0, source.length - visible.length);
  const aligned = sourceValues.slice(offset, offset + visible.length);
  while (aligned.length < visible.length) aligned.push(null);
  return aligned;
}

function buildChartEvents(payload) {
  const ev = [];
  (payload.financial_statements || []).forEach((f) => {
    if (f.source_updated_at) ev.push({ date: f.source_updated_at, type: "財報", label: `財報公布${f.quarter_label ? "（" + f.quarter_label + "）" : ""}` });
  });
  (payload.monthly_revenues || []).forEach((m) => {
    if (m.source_updated_at) ev.push({ date: m.source_updated_at, type: "營收", label: `月營收公布${m.year_month ? "（" + m.year_month + "）" : ""}` });
  });
  (payload.dividends || []).forEach((d) => {
    const dt = d.board_date;
    const isEx = String(d.period || "").includes("除息") || String(d.status || "").includes("除息");
    if (dt && isEx) ev.push({ date: dt, type: "除息", label: `除息${d.cash_dividend ? " " + d.cash_dividend + " 元" : ""}` });
  });
  return ev;
}

function dateDiffDays(a, b) {
  const da = new Date(a), db = new Date(b);
  if (Number.isNaN(da.getTime()) || Number.isNaN(db.getTime())) return Infinity;
  return Math.round((da - db) / 86400000);
}

function nearestChartIndex(dateStr) {
  const all = state.chartAll || [];
  if (!all.length || !dateStr) return -1;
  let best = -1, bestDiff = Infinity;
  for (let i = 0; i < all.length; i += 1) {
    const diff = Math.abs(dateDiffDays(all[i].date, dateStr));
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  }
  return bestDiff <= 7 ? best : -1;
}

function rebuildEventIndex() {
  const byIdx = {};
  const add = (e) => {
    const idx = nearestChartIndex(e.date);
    if (idx < 0) return;
    (byIdx[idx] = byIdx[idx] || []).push({ label: e.label, type: e.type });
  };
  (state.chartLocalEvents || []).forEach(add);
  (state.chartNewsEvents || []).forEach(add);
  state.chartEventsByIndex = byIdx;
}

function chartLayout(canvas) {
  const scale = window.devicePixelRatio || 1;
  const width = canvas.width ? canvas.width / scale : canvas.getBoundingClientRect().width;
  const height = canvas.height ? canvas.height / scale : 440;
  const padding = { top: 16, right: 66, bottom: 24, left: 56 };
  const scenario = chartScenarioFanData();
  const futureWidth = state.chartLargeMode && scenario ? Math.min(150, Math.max(96, width * 0.12)) : 0;
  const innerWidth = Math.max(180, width - padding.left - padding.right - futureWidth);
  const hidden = state.chartSeriesHidden || {};
  const showVol = state.chartLargeMode ? chartVolumeLayerEnabled() : !hidden.vol;
  const subplots = state.chartLargeMode ? activeChartSubplots() : [];
  const gap = 14;
  const volH = showVol ? 72 : 0;
  const subH = subplots.length ? subplots.length * 76 : 0;
  const extra = (showVol ? gap : 0) + (subplots.length ? gap * subplots.length : 0);
  const priceH = Math.max(160, height - padding.top - padding.bottom - volH - subH - extra);
  let y = padding.top;
  const price = { top: y, height: priceH }; y += priceH;
  let vol = null;
  if (showVol) { y += gap; vol = { top: y, height: volH }; y += volH; }
  const subplotLayouts = [];
  subplots.forEach((subplot) => {
    y += gap;
    subplotLayouts.push({ ...subplot, top: y, height: 76 });
    y += 76;
  });
  return {
    width,
    height,
    padding,
    innerWidth,
    futureWidth,
    plotRight: padding.left + innerWidth,
    price,
    vol,
    subplots: subplotLayouts,
    chips: null,
  };
}

function activeChartSubplots() {
  if (!state.chartLargeMode) return [];
  const catalog = state.chartCatalog || {};
  const features = Array.isArray(catalog.features) ? catalog.features : [];
  const categories = new Map((Array.isArray(catalog.categories) ? catalog.categories : []).map((item) => [item.key, item]));
  const groups = new Map();
  features
    .filter((feature) => feature.display_type === "subplot")
    .filter((feature) => !CHART_VOLUME_MA_KEYS.includes(feature.key))
    .filter((feature) => indicatorEnabled(feature.key) && featureSeries(feature.key).some((value) => value != null))
    .forEach((feature) => {
      const groupKey = feature.category || "subplot";
      if (!groups.has(groupKey)) {
        const axis = subplotAxisDefaults(groupKey);
        groups.set(groupKey, {
          key: groupKey,
          label: categories.get(groupKey)?.label || feature.category || "副圖",
          keys: [],
          color: axis.color,
          min: axis.min,
          max: axis.max,
        });
      }
      groups.get(groupKey).keys.push(feature.key);
    });
  return Array.from(groups.values());
}

function subplotAxisDefaults(groupKey) {
  const defaults = {
    rsi: { min: 0, max: 100, color: "#2f63a3" },
    kd: { min: 0, max: 100, color: "#C77D11" },
    macd: { color: "#6B4FA0" },
    volatility: { color: "#B0820B" },
    volume_price: { color: "#1C3D5A" },
    trend: { color: "#7a4fb0" },
  };
  return defaults[groupKey] || { color: "#2f63a3" };
}

function chartVolumeLayerEnabled() {
  return indicatorEnabled("vol") || CHART_VOLUME_MA_KEYS.some((key) => indicatorEnabled(key));
}

function chartView() {
  const n = (state.chartAll || []).length;
  let v = state.chartView || { start: 0, end: Math.max(0, n - 1) };
  let start = Math.max(0, Math.min(v.start, Math.max(0, n - 1)));
  let end = Math.max(start, Math.min(v.end, Math.max(0, n - 1)));
  return { start, end };
}

function chartXOf(i, view, layout) {
  const count = view.end - view.start;
  const denom = count > 0 ? count : 1;
  return layout.padding.left + (layout.innerWidth * (i - view.start)) / denom;
}

function chartValueForScale(value, basePrice = state._chartBasePrice || 1) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return NaN;
  const scaleMode = state.chartLargeMode ? state.chartScale : "price";
  if (scaleMode === "log") return Math.log(number);
  if (scaleMode === "percent") return basePrice > 0 ? (number / basePrice - 1) * 100 : NaN;
  return number;
}

function formatChartAxisValue(value, basePrice = state._chartBasePrice || 1) {
  const scaleMode = state.chartLargeMode ? state.chartScale : "price";
  if (scaleMode === "log") return formatNumber(Math.exp(value));
  if (scaleMode === "percent") return `${value > 0 ? "+" : ""}${formatNumber(value)}%`;
  return formatNumber(value);
}

function drawChart() {
  const canvas = elements.priceChart;
  if (!canvas) return;
  const colors = chartThemeColors();
  const all = state.chartAll || [];
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.max(720, Math.floor((rect.width || 960) * scale));
  canvas.height = Math.floor((rect.height || 440) * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const layout = chartLayout(canvas);
  ctx.clearRect(0, 0, layout.width, layout.height);
  ctx.fillStyle = colors.canvasBg;
  ctx.fillRect(0, 0, layout.width, layout.height);
  if (all.length < 2) {
    ctx.fillStyle = colors.muted;
    ctx.font = "13px Microsoft JhengHei, Segoe UI, Arial";
    ctx.fillText("尚無足夠資料", layout.padding.left, layout.price.top + 24);
    return;
  }
  const view = chartView();
  const slot = layout.innerWidth / Math.max(1, view.end - view.start + 1);

  drawPricePanel(ctx, layout, view, slot);
  state.chartSRLines = [];
  if (!(state.chartSeriesHidden && state.chartSeriesHidden.sr)) drawSupportResistance(ctx, layout, view);
  if (state.chartLargeMode) drawScenarioFan(ctx, layout, view);
  if (layout.vol) drawVolPanel(ctx, layout, view, slot);
  if (state.chartLargeMode) {
    drawIndicatorSubplots(ctx, layout, view);
    drawChartAnnotations(ctx, layout, view);
  }
  drawEventMarkers(ctx, layout, view);
  drawRangeSelection(ctx, layout, view, slot);
  drawCrosshairTooltip(ctx, layout, view);
  drawHoverFeatureBadge(ctx, layout);
  window.drawChartTourOverlay?.(ctx, layout, view);
}

function drawPricePanel(ctx, layout, view, slot) {
  const all = state.chartAll;
  const colors = chartThemeColors();
  const panel = layout.price;
  const hidden = state.chartSeriesHidden || {};
  const sourceSeries = state.chartLargeMode ? (state.chartMA || []) : (state.chartClassicMA || state.chartMA || []);
  const mas = sourceSeries.filter((s) => state.chartLargeMode ? indicatorEnabled(s.key) : !hidden[s.key]);
  const basePrice = Number(all[view.start]?.close) || 1;
  state._chartBasePrice = basePrice;
  let hi = -Infinity, lo = Infinity;
  for (let i = view.start; i <= view.end; i += 1) {
    hi = Math.max(hi, chartValueForScale(Number(all[i].high), basePrice));
    lo = Math.min(lo, chartValueForScale(Number(all[i].low), basePrice));
    mas.forEach((s) => {
      const v = chartValueForScale(Number(s.values[i]), basePrice);
      if (Number.isFinite(v)) { hi = Math.max(hi, v); lo = Math.min(lo, v); }
    });
  }
  const scenario = chartScenarioFanData();
  if (state.chartLargeMode && scenario && view.end >= all.length - 1) {
    scenario.windows.forEach((windowStats) => {
      ["p10", "p25", "median", "p75", "p90"].forEach((key) => {
        const price = scenarioPriceAtReturn(scenario.latestClose, windowStats[key]);
        const scaled = chartValueForScale(price, basePrice);
        if (Number.isFinite(scaled)) {
          hi = Math.max(hi, scaled);
          lo = Math.min(lo, scaled);
        }
      });
    });
  }
  const rng = (hi - lo) || 1;
  const min = lo - rng * 0.06, max = hi + rng * 0.06, range = (max - min) || 1;
  const yOfScaled = (v) => panel.top + panel.height - ((v - min) / range) * panel.height;
  const yOf = (v) => yOfScaled(chartValueForScale(Number(v), basePrice));
  state._priceYOf = yOf;

  ctx.strokeStyle = colors.grid; ctx.lineWidth = 1;
  ctx.fillStyle = colors.muted; ctx.font = "11px Microsoft JhengHei, Segoe UI, Arial";
  for (let g = 0; g <= 4; g += 1) {
    const y = panel.top + (panel.height * g) / 4;
    ctx.beginPath(); ctx.moveTo(layout.padding.left, y); ctx.lineTo(layout.width - layout.padding.right, y); ctx.stroke();
    ctx.fillText(formatChartAxisValue(max - (range * g) / 4, basePrice), layout.width - layout.padding.right + 6, y + 4);
  }
  // 日期軸（首尾）
  ctx.fillStyle = colors.muted;
  ctx.fillText(all[view.start].date, layout.padding.left, layout.height - 8);
  const lastLabel = all[view.end].date;
  ctx.fillText(lastLabel, layout.width - layout.padding.right - ctx.measureText(lastLabel).width, layout.height - 8);

  // 蠟燭
  const cw = Math.max(1, Math.min(11, slot * 0.68));
  for (let i = view.start; i <= view.end; i += 1) {
    const p = all[i];
    const o = Number(p.open), h = Number(p.high), l = Number(p.low), c = Number(p.close);
    const x = chartXOf(i, view, layout);
    const color = c > o ? CANDLE_UP_COLOR : c < o ? CANDLE_DOWN_COLOR : CANDLE_FLAT_COLOR;
    const provisional = Boolean(p.provisional);
    ctx.save();
    if (provisional) {
      ctx.globalAlpha = .82;
      ctx.setLineDash([3, 2]);
    }
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, yOf(h)); ctx.lineTo(x, yOf(l)); ctx.stroke();
    const top = Math.min(yOf(o), yOf(c)), bh = Math.max(1, Math.abs(yOf(c) - yOf(o)));
    if (provisional) {
      ctx.setLineDash([]);
      ctx.lineWidth = 1.4;
      ctx.strokeRect(x - cw / 2, top, cw, bh);
    } else {
      ctx.fillRect(x - cw / 2, top, cw, bh);
    }
    ctx.restore();
  }
  // 均線
  mas.slice().reverse().forEach((s) => {
    const emphasis = activeChartEmphasisFeature();
    ctx.save(); ctx.strokeStyle = s.color; ctx.lineWidth = emphasis === s.key ? (s.width || 1) + 1.4 : s.width; ctx.lineCap = "round"; ctx.lineJoin = "round";
    if (emphasis && emphasis !== s.key) ctx.globalAlpha = .28;
    if (s.dash) ctx.setLineDash(s.dash);
    let started = false; ctx.beginPath();
    for (let i = view.start; i <= view.end; i += 1) {
      const v = s.values[i];
      if (v == null || !Number.isFinite(v)) { started = false; continue; }
      const x = chartXOf(i, view, layout), y = yOf(v);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    }
    ctx.stroke(); ctx.restore();
  });
}

function drawScenarioFan(ctx, layout, view) {
  const scenario = chartScenarioFanData();
  const yOf = state._priceYOf;
  const all = state.chartAll || [];
  if (!scenario || !yOf || !layout.futureWidth || view.end < all.length - 1) return;
  const originIndex = all.length - 1;
  const originX = chartXOf(originIndex, view, layout);
  const originY = yOf(scenario.latestClose);
  const right = layout.width - layout.padding.right;
  const maxDays = Math.max(...scenario.windows.map((item) => item.days), 1);
  const xOfDays = (days) => originX + ((right - originX) * Number(days)) / maxDays;
  const point = (item, key) => ({
    x: xOfDays(item.days),
    y: clamp(yOf(scenarioPriceAtReturn(scenario.latestClose, item[key])), layout.price.top, layout.price.top + layout.price.height),
  });
  const drawBand = (lowKey, highKey, fillStyle) => {
    const upper = [{ x: originX, y: originY }, ...scenario.windows.map((item) => point(item, highKey))];
    const lower = [{ x: originX, y: originY }, ...scenario.windows.map((item) => point(item, lowKey))].reverse();
    ctx.beginPath();
    upper.forEach((p, index) => { if (index === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
    lower.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.closePath();
    ctx.fillStyle = fillStyle;
    ctx.fill();
  };
  ctx.save();
  drawBand("p10", "p90", "rgba(125,184,226,.16)");
  drawBand("p25", "p75", "rgba(125,184,226,.32)");
  const medianWindows = scenario.windows.filter((item) => item.count >= 8 && Number.isFinite(item.median));
  if (medianWindows.length) {
    ctx.strokeStyle = "rgba(44,84,117,.78)";
    ctx.lineWidth = 1.2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(originX, originY);
    medianWindows.forEach((item) => {
      const p = point(item, "median");
      ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.font = "10.5px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillStyle = "rgba(44,84,117,.88)";
  ctx.fillText("歷史範圍", Math.min(originX + 8, right - 58), layout.price.top + 14);
  ctx.fillStyle = "rgba(122,135,150,.95)";
  ctx.fillText("非預測", Math.min(originX + 8, right - 42), layout.price.top + 28);
  scenario.windows.forEach((item) => {
    const x = xOfDays(item.days);
    ctx.fillStyle = "rgba(122,135,150,.9)";
    ctx.fillText(`${formatInteger(item.days)}日`, Math.min(x - 12, right - 26), layout.price.top + layout.price.height - 6);
  });
  ctx.restore();
}

function drawVolPanel(ctx, layout, view, slot) {
  const all = state.chartAll, panel = layout.vol;
  const colors = chartThemeColors();
  const volumeMaLayers = state.chartLargeMode
    ? CHART_VOLUME_MA_KEYS.filter((key) => indicatorEnabled(key) && featureSeries(key).some((value) => value != null))
    : [];
  let vmax = 1;
  for (let i = view.start; i <= view.end; i += 1) vmax = Math.max(vmax, Number(all[i].volume) || 0);
  volumeMaLayers.forEach((key) => {
    const values = featureSeries(key);
    for (let i = view.start; i <= view.end; i += 1) {
      const value = Number(values[i]);
      if (Number.isFinite(value)) vmax = Math.max(vmax, value);
    }
  });
  ctx.fillStyle = colors.muted2; ctx.font = "10.5px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillText("量", layout.padding.left, panel.top - 2);
  const bw = Math.max(1, Math.min(11, slot * 0.68));
  for (let i = view.start; i <= view.end; i += 1) {
    const p = all[i], v = Number(p.volume) || 0;
    const bh = (v / vmax) * panel.height;
    const x = chartXOf(i, view, layout);
    const up = Number(p.close) >= Number(p.open);
    ctx.globalAlpha = p.provisional ? .42 : 1;
    ctx.fillStyle = up ? "rgba(224,49,49,0.45)" : "rgba(47,158,68,0.45)";
    ctx.fillRect(x - bw / 2, panel.top + panel.height - bh, bw, bh);
  }
  ctx.globalAlpha = 1;
  volumeMaLayers.forEach((key) => {
    const style = CHART_VOLUME_MA_STYLES[key] || { color: colors.brand, width: 1.1 };
    const values = featureSeries(key);
    const yOf = (value) => panel.top + panel.height - (value / vmax) * panel.height;
    drawNumericLine(ctx, values, view, layout, yOf, focusedLineStyle(key, style));
  });
}

function drawIndicatorSubplots(ctx, layout, view) {
  (layout.subplots || []).forEach((panel) => drawIndicatorSubplot(ctx, layout, view, panel));
}

function drawIndicatorSubplot(ctx, layout, view, panel) {
  const colors = chartThemeColors();
  const enabledKeys = panel.keys.filter((key) => indicatorEnabled(key) && featureSeries(key).some((value) => value != null));
  if (!enabledKeys.length) return;
  let min = Number.isFinite(panel.min) ? Number(panel.min) : Infinity;
  let max = Number.isFinite(panel.max) ? Number(panel.max) : -Infinity;
  enabledKeys.forEach((key) => {
    const values = featureSeries(key);
    for (let i = view.start; i <= view.end; i += 1) {
      const value = Number(values[i]);
      if (Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  });
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    min = min === Infinity ? 0 : min - 1;
    max = max === -Infinity ? 1 : max + 1;
  }
  const pad = (max - min) * 0.12 || 1;
  if (!Number.isFinite(panel.min)) min -= pad;
  if (!Number.isFinite(panel.max)) max += pad;
  const yOf = (value) => panel.top + panel.height - ((value - min) / ((max - min) || 1)) * panel.height;

  ctx.save();
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(layout.padding.left, panel.top);
  ctx.lineTo(layout.width - layout.padding.right, panel.top);
  ctx.moveTo(layout.padding.left, panel.top + panel.height);
  ctx.lineTo(layout.width - layout.padding.right, panel.top + panel.height);
  ctx.stroke();
  ctx.fillStyle = colors.muted;
  ctx.font = "10.5px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillText(panel.label, layout.padding.left, panel.top - 3);
  ctx.fillText(formatNumber(max), layout.width - layout.padding.right + 6, panel.top + 8);
  ctx.fillText(formatNumber(min), layout.width - layout.padding.right + 6, panel.top + panel.height);

  if (panel.key === "rsi" || panel.key === "kd") {
    [20, 50, 80].forEach((level) => {
      if (level < min || level > max) return;
      const y = yOf(level);
      ctx.strokeStyle = level === 50 ? colors.line : colors.grid;
      ctx.setLineDash([3, 4]);
      ctx.beginPath(); ctx.moveTo(layout.padding.left, y); ctx.lineTo(layout.width - layout.padding.right, y); ctx.stroke();
      ctx.setLineDash([]);
    });
  }

  enabledKeys.forEach((key, index) => {
    const values = featureSeries(key);
    if (key === "macd_histogram") {
      const slot = layout.innerWidth / Math.max(1, view.end - view.start + 1);
      const bw = Math.max(1, Math.min(8, slot * 0.56));
      const zeroY = yOf(0);
      for (let i = view.start; i <= view.end; i += 1) {
        const value = Number(values[i]);
        if (!Number.isFinite(value)) continue;
        const x = chartXOf(i, view, layout);
        const y = yOf(value);
        ctx.fillStyle = value >= 0 ? "rgba(224,49,49,.45)" : "rgba(47,158,68,.45)";
        ctx.fillRect(x - bw / 2, Math.min(y, zeroY), bw, Math.max(1, Math.abs(zeroY - y)));
      }
      return;
    }
    const style = focusedLineStyle(key, subplotLineStyle(key, index, panel.color));
    drawNumericLine(ctx, values, view, layout, yOf, style);
  });
  ctx.restore();
}

function focusedLineStyle(key, style) {
  const emphasis = activeChartEmphasisFeature();
  if (!emphasis) return style;
  if (emphasis === key) {
    return { ...style, width: (style.width || 1.2) + 1.2, alpha: 1 };
  }
  return { ...style, alpha: .28 };
}

function activeChartEmphasisFeature() {
  return state.chartFocusedFeature || state.chartHoverFeatureKey || null;
}

function subplotLineStyle(key, index, fallback) {
  const colors = {
    rsi_14: "#2f63a3", rsi_6: "#c47b2a", rsi_12: "#1f7a5f", rsi_24: "#7a4fb0",
    macd: "#6B4FA0", macd_signal: "#C77D11",
    kd_k: "#2f63a3", kd_d: "#C77D11", kd_j: "#7a4fb0",
    atr_5: "#d08c60", atr_14: "#B0820B", atr_20: "#8a6d1b",
    hv_20: "#2C5475", hv_60: "#7a4fb0", hv_120: "#315b7c",
    obv: "#1C3D5A",
    trend_strength: "#7a4fb0",
  };
  return { color: colors[key] || fallback || ["#2f63a3", "#C77D11", "#7a4fb0"][index % 3], width: 1.3 };
}

function drawNumericLine(ctx, values, view, layout, yOf, style) {
  ctx.save();
  ctx.strokeStyle = style.color;
  ctx.lineWidth = style.width || 1.2;
  if (style.alpha != null) ctx.globalAlpha = style.alpha;
  if (style.dash) ctx.setLineDash(style.dash);
  ctx.beginPath();
  let started = false;
  for (let i = view.start; i <= view.end; i += 1) {
    const value = Number(values[i]);
    if (!Number.isFinite(value)) { started = false; continue; }
    const x = chartXOf(i, view, layout);
    const y = yOf(value);
    if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.restore();
}

function drawChipsPanel(ctx, layout, view, slot) {
  const all = state.chartAll, chips = state.chartChips, panel = layout.chips;
  const colors = chartThemeColors();
  const mid = panel.top + panel.height / 2;
  const keys = ["foreign_net", "trust_net", "dealer_net"];
  const grouped = slot >= 9; // 夠寬才畫三家，否則畫合計
  let maxAbs = 1;
  for (let i = view.start; i <= view.end; i += 1) {
    const c = chips[all[i].date]; if (!c) continue;
    if (grouped) keys.forEach((k) => { maxAbs = Math.max(maxAbs, Math.abs(Number(c[k]) || 0)); });
    else maxAbs = Math.max(maxAbs, Math.abs(Number(c.total_net) || 0));
  }
  // 零軸
  ctx.strokeStyle = colors.line; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(layout.padding.left, mid); ctx.lineTo(layout.width - layout.padding.right, mid); ctx.stroke();
  // 標題 + 小圖例
  ctx.font = "10.5px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillStyle = colors.muted;
  ctx.fillText("三大法人買賣超（上買下賣，張）", layout.padding.left, panel.top - 2);
  if (grouped) {
    let lx = layout.width - layout.padding.right - 168;
    keys.forEach((k) => { ctx.fillStyle = INST_COLORS[k]; ctx.fillRect(lx, panel.top - 9, 9, 8); ctx.fillStyle = colors.muted; ctx.fillText(INST_LABELS[k], lx + 12, panel.top - 2); lx += 56; });
  }
  ctx.fillStyle = colors.muted; ctx.font = "10px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillText(Math.round(maxAbs / 1000).toLocaleString("zh-TW"), layout.width - layout.padding.right + 6, panel.top + 9);
  const half = panel.height / 2 - 4;
  const barOf = (v) => (Math.abs(v) / maxAbs) * half;
  if (grouped) {
    const groupW = Math.min(slot * 0.8, 18);
    const bw = Math.max(1.2, groupW / 3 - 0.6);
    for (let i = view.start; i <= view.end; i += 1) {
      const c = chips[all[i].date]; if (!c) continue;
      const x = chartXOf(i, view, layout);
      keys.forEach((k, ki) => {
        const v = Number(c[k]) || 0; if (!v) return;
        const bx = x - groupW / 2 + ki * (bw + 0.6);
        const bh = barOf(v);
        ctx.fillStyle = INST_COLORS[k];
        if (v > 0) ctx.fillRect(bx, mid - bh, bw, bh); else ctx.fillRect(bx, mid, bw, bh);
      });
    }
  } else {
    const bw = Math.max(1, Math.min(11, slot * 0.68));
    for (let i = view.start; i <= view.end; i += 1) {
      const c = chips[all[i].date]; if (!c) continue;
      const v = Number(c.total_net) || 0; if (!v) continue;
      const x = chartXOf(i, view, layout), bh = barOf(v);
      ctx.fillStyle = v > 0 ? colors.brand : colors.warn;
      if (v > 0) ctx.fillRect(x - bw / 2, mid - bh, bw, bh); else ctx.fillRect(x - bw / 2, mid, bw, bh);
    }
  }
}

function drawEventMarkers(ctx, layout, view) {
  const byIdx = state.chartEventsByIndex || {};
  const y = layout.price.top + 2;
  Object.keys(byIdx).forEach((key) => {
    const i = Number(key);
    if (i < view.start || i > view.end) return;
    const evs = byIdx[key];
    const risky = evs.some((e) => e.type === "風險");
    const color = risky ? EVENT_COLORS["風險"] : (EVENT_COLORS[evs[0].type] || "#2C5475");
    const x = chartXOf(i, view, layout);
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.moveTo(x, y + 8); ctx.lineTo(x - 4, y); ctx.lineTo(x + 4, y); ctx.closePath(); ctx.fill();
  });
}

function drawChartAnnotations(ctx, layout, view) {
  const annotations = Array.isArray(state.chartAnnotations) ? state.chartAnnotations : [];
  if (!annotations.length || !state._priceYOf) return;
  const all = state.chartAll || [];
  ctx.save();
  annotations.forEach((annotation) => {
    const idx = annotationIndex(annotation.anchor_date);
    if (idx < 0 || idx < view.start || idx > view.end) return;
    const x = chartXOf(idx, view, layout);
    const price = Number(annotation.anchor_price || all[idx]?.close);
    if (!Number.isFinite(price) || price <= 0) return;
    const y = state._priceYOf(price);
    const color = annotation.color || "#2C5475";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1.4;
    if (annotation.kind === "hline") {
      ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(layout.padding.left, y); ctx.lineTo(layout.width - layout.padding.right, y); ctx.stroke();
      ctx.setLineDash([]);
      drawAnnotationLabel(ctx, annotation, layout.padding.left + 6, y - 6, color);
      return;
    }
    if (annotation.kind === "trendline" || annotation.kind === "arrow") {
      const idx2 = annotationIndex(annotation.anchor_date2);
      if (idx2 >= 0) {
        const x2 = chartXOf(Math.max(view.start, Math.min(view.end, idx2)), view, layout);
        const price2 = Number(annotation.anchor_price2 || price);
        const y2 = state._priceYOf(price2);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
        if (annotation.kind === "arrow") drawArrowHead(ctx, x, y, x2, y2, color);
        drawAnnotationLabel(ctx, annotation, x2 + 5, y2 - 6, color);
        return;
      }
    }
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.85)";
    ctx.lineWidth = 1;
    ctx.stroke();
    drawAnnotationLabel(ctx, annotation, x + 7, y - 7, color);
  });
  ctx.restore();
}

function drawAnnotationLabel(ctx, annotation, x, y, color) {
  const text = String(annotation.text || annotationKindLabel(annotation.kind) || "").trim();
  if (!text) return;
  ctx.save();
  ctx.font = "11px Microsoft JhengHei, Segoe UI, Arial";
  const width = Math.min(180, ctx.measureText(text).width + 12);
  ctx.fillStyle = "rgba(255,255,255,.88)";
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath(); roundedRect(ctx, x, y - 14, width, 20, 5); ctx.fill(); ctx.stroke();
  ctx.fillStyle = color;
  ctx.fillText(text.length > 18 ? `${text.slice(0, 18)}...` : text, x + 6, y);
  ctx.restore();
}

function drawArrowHead(ctx, x1, y1, x2, y2, color) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 8;
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - size * Math.cos(angle - Math.PI / 6), y2 - size * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - size * Math.cos(angle + Math.PI / 6), y2 - size * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function annotationIndex(dateStr) {
  const all = state.chartAll || [];
  if (!dateStr) return -1;
  return all.findIndex((item) => item.date === dateStr);
}

function annotationKindLabel(kind) {
  return { note: "筆記", hline: "水平線", trendline: "趨勢線", arrow: "箭頭", textbox: "文字框" }[kind] || "標註";
}

function renderAnnotationList() {
  if (!elements.annotationList) return;
  const items = Array.isArray(state.chartAnnotations) ? state.chartAnnotations : [];
  if (!items.length) {
    elements.annotationList.innerHTML = `<p class="annotation-empty">目前沒有圖表標註。</p>`;
    return;
  }
  elements.annotationList.innerHTML = items.map((item) => `
    <div class="annotation-item">
      <strong>${escapeHtml(annotationKindLabel(item.kind))}</strong>
      <span>${escapeHtml(item.anchor_date || "--")} ${escapeHtml(item.text || "")}</span>
      <div>
        <button type="button" onclick="editChartAnnotation(${Number(item.id)})">編輯</button>
        <button type="button" onclick="deleteChartAnnotation(${Number(item.id)})">刪除</button>
      </div>
    </div>
  `).join("");
}

async function addChartAnnotationFromUI() {
  if (!state.activeStockId || !(state.chartAll || []).length) return;
  const kind = elements.annotationKind?.value || "note";
  const text = elements.annotationText?.value || "";
  const all = state.chartAll || [];
  const range = normalizeChartRange(state.chartRangeSelection?.start, state.chartRangeSelection?.end);
  const index = state.chartHoverIndex != null ? state.chartHoverIndex : (range?.start ?? all.length - 1);
  const anchor = all[index] || all[all.length - 1];
  const payload = {
    kind,
    anchor_date: anchor.date,
    anchor_price: Number(anchor.close),
    text,
    color: kind === "hline" ? "#B0820B" : "#2C5475",
  };
  if (["trendline", "arrow"].includes(kind)) {
    const endIndex = range?.end ?? Math.min(all.length - 1, index + 20);
    const end = all[endIndex] || anchor;
    payload.anchor_date2 = end.date;
    payload.anchor_price2 = Number(end.close);
  }
  try {
    const saved = await postJson(`/api/stocks/${encodeURIComponent(state.activeStockId)}/annotations`, payload);
    state.chartAnnotations = [...(state.chartAnnotations || []), saved];
    if (elements.annotationText) elements.annotationText.value = "";
    renderAnnotationList();
    drawChart();
  } catch (error) {
    showMessage(`新增標註失敗：${error.message}`, true);
  }
}

async function editChartAnnotation(id) {
  const current = (state.chartAnnotations || []).find((item) => Number(item.id) === Number(id));
  if (!current || !state.activeStockId) return;
  const nextText = window.prompt("更新標註文字", current.text || "");
  if (nextText == null) return;
  try {
    const updated = await patchJson(`/api/stocks/${encodeURIComponent(state.activeStockId)}/annotations/${id}`, { text: nextText });
    state.chartAnnotations = (state.chartAnnotations || []).map((item) => Number(item.id) === Number(id) ? updated : item);
    renderAnnotationList();
    drawChart();
  } catch (error) {
    showMessage(`更新標註失敗：${error.message}`, true);
  }
}

async function deleteChartAnnotation(id) {
  if (!state.activeStockId) return;
  try {
    await deleteJson(`/api/stocks/${encodeURIComponent(state.activeStockId)}/annotations/${id}`);
    state.chartAnnotations = (state.chartAnnotations || []).filter((item) => Number(item.id) !== Number(id));
    renderAnnotationList();
    drawChart();
  } catch (error) {
    showMessage(`刪除標註失敗：${error.message}`, true);
  }
}

function activeChartRangeSelection() {
  return state.chartRangeDraft || state.chartRangeSelection || null;
}

function normalizeChartRange(start, end) {
  const all = state.chartAll || [];
  if (!all.length) return null;
  let a = Math.max(0, Math.min(all.length - 1, Number(start)));
  let b = Math.max(0, Math.min(all.length - 1, Number(end)));
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  if (a > b) [a, b] = [b, a];
  return { start: a, end: b };
}

function drawRangeSelection(ctx, layout, view, slot) {
  const range = activeChartRangeSelection();
  if (!range) return;
  const colors = chartThemeColors();
  const start = Math.max(range.start, view.start);
  const end = Math.min(range.end, view.end);
  if (start > end) return;
  const left = Math.max(layout.padding.left, chartXOf(start, view, layout) - slot / 2);
  const right = Math.min(layout.width - layout.padding.right, chartXOf(end, view, layout) + slot / 2);
  const top = layout.price.top;
  const bottom = layout.vol ? layout.vol.top + layout.vol.height : layout.price.top + layout.price.height;
  ctx.save();
  ctx.fillStyle = colors.rangeFill;
  ctx.strokeStyle = colors.rangeStroke;
  ctx.lineWidth = 1;
  ctx.fillRect(left, top, Math.max(2, right - left), bottom - top);
  ctx.strokeRect(left + 0.5, top + 0.5, Math.max(1, right - left - 1), bottom - top - 1);
  ctx.restore();
}

function chartIndexAtClientX(clientX) {
  const canvas = elements.priceChart;
  const rect = canvas.getBoundingClientRect();
  const layout = chartLayout(canvas);
  const view = chartView();
  const localX = ((clientX - rect.left) / rect.width) * layout.width;
  const ratio = (localX - layout.padding.left) / layout.innerWidth;
  const count = view.end - view.start;
  let idx = view.start + Math.round(ratio * count);
  return Math.max(view.start, Math.min(view.end, idx));
}

function drawCrosshairTooltip(ctx, layout, view) {
  const idx = state.chartHoverIndex;
  if (idx == null || idx < view.start || idx > view.end) return;
  const colors = chartThemeColors();
  const all = state.chartAll, item = all[idx];
  const x = chartXOf(idx, view, layout);
  ctx.save();
  ctx.strokeStyle = colors.rangeStroke; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(x, layout.price.top); ctx.lineTo(x, layout.height - layout.padding.bottom); ctx.stroke();
  ctx.setLineDash([]);

  const o = Number(item.open), h = Number(item.high), l = Number(item.low), c = Number(item.close);
  const prev = idx > 0 ? Number(all[idx - 1].close) : null;
  const chg = prev != null && Number.isFinite(prev) ? c - prev : null;
  const chgPct = chg != null && prev ? (chg / prev) * 100 : null;
  const lots = Math.round((Number(item.volume) || 0) / 1000);
  const provisional = Boolean(item.provisional);
  const head = `${item.date}　${provisional ? "盤中暫算" : (c > o ? "收漲" : c < o ? "收跌" : "持平")}`;
  const lines = [
    `開 ${formatNumber(o)}　${provisional ? "暫收" : "收"} ${formatNumber(c)}`,
    `高 ${formatNumber(h)}　低 ${formatNumber(l)}`,
    chg == null ? "漲跌 --" : `漲跌 ${chg > 0 ? "+" : ""}${formatNumber(chg)}（${chgPct > 0 ? "+" : ""}${formatNumber(chgPct)}%）`,
    `量 ${lots.toLocaleString("zh-TW")} 張`,
  ];
  if (provisional) lines.push("收盤後正式日線可能不同");
  const chip = (state.chartChips || {})[item.date];
  if (chip) {
    lines.push(`外資 ${formatLots(chip.foreign_net)}　投信 ${formatLots(chip.trust_net)}`);
    lines.push(`自營 ${formatLots(chip.dealer_net)}　三大 ${formatLots(chip.total_net)} 張`);
  }
  collectTooltipIndicators(idx).forEach((line) => lines.push(line));
  const evs = (state.chartEventsByIndex || {})[idx] || [];
  evs.slice(0, 3).forEach((e) => lines.push(`◆ ${e.label}`));

  const lh = 17, pad = 10, w = 260;
  const hgt = pad * 2 + 20 + lines.length * lh;
  let tx = x + 12; if (tx + w > layout.width - 6) tx = x - w - 12;
  let ty = layout.price.top + 6;
  ctx.fillStyle = colors.tooltipBg; ctx.beginPath(); roundedRect(ctx, tx, ty, w, hgt, 8); ctx.fill();
  ctx.fillStyle = colors.tooltipText; ctx.font = "13px Microsoft JhengHei, Segoe UI, Arial";
  ctx.fillText(head, tx + pad, ty + pad + 12);
  ctx.font = "12px Microsoft JhengHei, Segoe UI, Arial";
  lines.forEach((ln, i) => {
    if (ln.startsWith("◆")) ctx.fillStyle = colors.tooltipAccent; else ctx.fillStyle = colors.tooltipText;
    ctx.fillText(ln, tx + pad, ty + pad + 20 + (i + 1) * lh - 4);
  });
  ctx.restore();
}

function drawHoverFeatureBadge(ctx, layout) {
  if (!state.chartLargeMode || !state.chartHoverFeatureKey || !state.chartHoverPoint) return;
  const text = hoverFeatureSummary(state.chartHoverFeatureKey, state.chartHoverFeatureIndex);
  if (!text) return;
  const colors = chartThemeColors();
  const padX = 9;
  const h = 26;
  ctx.save();
  ctx.font = "12px Microsoft JhengHei, Segoe UI, Arial";
  const w = Math.min(360, ctx.measureText(text).width + padX * 2);
  let x = state.chartHoverPoint.x + 12;
  let y = state.chartHoverPoint.y - h - 8;
  if (x + w > layout.width - 8) x = layout.width - w - 8;
  if (y < 8) y = state.chartHoverPoint.y + 14;
  ctx.fillStyle = colors.tooltipBg;
  ctx.beginPath();
  roundedRect(ctx, x, y, w, h, 8);
  ctx.fill();
  ctx.strokeStyle = colors.rangeStroke;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = colors.tooltipText;
  ctx.fillText(text.length > 42 ? `${text.slice(0, 42)}...` : text, x + padX, y + 17);
  ctx.restore();
}

function hoverFeatureSummary(key, index) {
  const srLine = findSupportResistanceLine(key);
  if (srLine) return `${srLine.label} ${formatNumber(srLine.price)} · 近${srLine.window}日${srLine.kindLabel}${srLine.provisional ? " · 盤中暫算" : ""}`;
  const feature = chartFeatureSpec(key);
  const value = featureValueAtIndex(key, index);
  const valueText = formatIndicatorValue(key, value);
  const description = compactDescription(feature.description || feature.label || "");
  return `${feature.label || key} · ${valueText}${description ? ` · ${description}` : ""}`;
}

function compactDescription(text) {
  const first = String(text || "").split(/[。；]/)[0].replace(/\s+/g, " ").trim();
  return first.length > 18 ? `${first.slice(0, 18)}...` : first;
}

function featureValueAtIndex(key, index) {
  if (key === "vol") return (state.chartAll || [])[index]?.volume;
  const values = featureSeries(key);
  if (index != null && index >= 0 && index < values.length) return values[index];
  return latestFeatureRawValue(key);
}

function collectTooltipIndicators(index) {
  if (!state.chartLargeMode) return [];
  const catalog = state.chartCatalog || {};
  const features = Array.isArray(catalog.features) ? catalog.features : [];
  const preferred = features
    .filter((feature) => indicatorEnabled(feature.key))
    .filter(isChartVisualFeature)
    .slice(0, 8);
  const lines = [];
  preferred.forEach((feature) => {
    const value = featureSeries(feature.key)[index];
    if (value == null) return;
    if (typeof value === "object") {
      if (value.score != null) lines.push(`${feature.label} ${formatNumber(value.score)}分`);
      return;
    }
    if (typeof value === "boolean") {
      if (value) lines.push(`${feature.label} 是`);
      return;
    }
    if (Number.isFinite(Number(value))) {
      lines.push(`${feature.label} ${formatNumber(value)}`);
    }
  });
  return lines;
}

function renderRangeStatsPanel(range = state.chartRangeSelection || state.chartRangeDraft) {
  updateRangeControlState();
  const panel = elements.rangeStatsPanel;
  if (!panel) return;
  const normalized = range ? normalizeChartRange(range.start, range.end) : null;
  if (!normalized) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const stats = computeRangeStats(state.chartAll || [], normalized.start, normalized.end);
  if (!stats.available) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const changeClass = toneClass(stats.price_change);
  const rows = state.chartAll || [];
  const includesIntraday = Boolean(rows.slice(normalized.start, normalized.end + 1).some((item) => item?.provisional));
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="range-stats-head">
      <strong>${escapeHtml(stats.start_date || "--")} 至 ${escapeHtml(stats.end_date || "--")}</strong>
      <span>${formatInteger(stats.trading_days)} 個交易日</span>
    </div>
    <div class="range-stats-grid">
      ${rangeStatItem("起訖收盤", `${formatNumber(stats.start_price)} → ${formatNumber(stats.end_price)}`)}
      ${rangeStatItem("期間漲跌幅", `<span class="${changeClass}">${formatSignedPercent(stats.price_change_percent)}</span>`, true)}
      ${rangeStatItem("區間高低", `${formatNumber(stats.highest)} / ${formatNumber(stats.lowest)}`)}
      ${rangeStatItem("振幅", formatPercent(stats.amplitude_percent))}
      ${rangeStatItem("區間均量", formatAverageLots(stats.average_volume))}
      ${rangeStatItem("年化波動度", formatPercent(stats.annualized_volatility_percent))}
      ${rangeStatItem("區間 VWAP", formatNumber(stats.vwap))}
      ${rangeStatItem("漲跌點數", `<span class="${changeClass}">${formatSignedNumber(stats.price_change)}</span>`, true)}
    </div>
    <p class="range-stats-note">區間統計只整理框選期間已發生的價量資料${includesIntraday ? "；本區間含盤中暫算，收盤後可能改變" : ""}，不是預測，也不是買賣建議。</p>
  `;
}

function rangeStatItem(label, value, raw = false) {
  return `<div class="range-stat"><span>${escapeHtml(label)}</span><strong>${raw ? value : escapeHtml(value)}</strong></div>`;
}

function formatSignedNumber(value) {
  if (value == null || !Number.isFinite(Number(value))) return "--";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${formatNumber(n)}`;
}

function formatSignedPercent(value) {
  if (value == null || !Number.isFinite(Number(value))) return "--";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${formatNumber(n)}%`;
}

function formatAverageLots(value) {
  if (value == null || !Number.isFinite(Number(value))) return "--";
  return `${formatInteger(Math.round(Number(value) / 1000))} 張`;
}

function updateRangeControlState() {
  elements.chartRangeBtn?.classList.toggle("is-active", Boolean(state.chartRangeMode));
  elements.chartClearRangeBtn?.classList.toggle("hidden", !state.chartRangeSelection && !state.chartRangeDraft);
}

function toggleLargeChart(force) {
  const panel = elements.priceChart?.closest(".chart-panel");
  if (!panel) return;
  const entering = typeof force === "boolean" ? force : !state.chartLargeMode;
  state.chartLargeMode = entering;
  if (entering) window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  panel.classList.toggle("chart-lab-mode", entering);
  document.body.classList.toggle("chart-lab-open", entering);
  elements.chartLargeBtn?.classList.toggle("is-active", entering);
  if (elements.chartLargeBtn) elements.chartLargeBtn.textContent = entering ? "關閉大型圖" : "大型K線圖";
  setChartUxMode(state.chartPrefs?.ux_mode || "translate", { persist: false, redraw: false });
  if (!entering && document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
  if (!entering) window.stopChartTour?.({ silent: true });
  renderIndicatorPanel();
  renderChartTranslation(state.activePayload);
  refreshIntradayChartLayer({ preserveView: true, redraw: false });
  window.syncChartTourUi?.();
  updateChartLegendState();
  window.setTimeout(drawChart, 80);
}

function toggleChartFullscreen() {
  toggleLargeChart();
}

// ---- 互動：滾輪縮放 / 拖曳平移 / hover ----
function handleChartPointerMove(event) {
  if (state.chartSelectingRange) { doChartRangeSelect(event); return; }
  if (state.chartDragging) { doChartPan(event); return; }
  const all = state.chartAll || [];
  if (all.length < 2) return;
  const idx = chartIndexAtClientX(event.clientX);
  const target = state.chartLargeMode ? nearestChartFeatureAtPointer(event) : null;
  const nextFeature = target?.key && target.key !== "candle" ? target.key : null;
  const point = chartLocalPoint(event);
  const changed = idx !== state.chartHoverIndex
    || nextFeature !== state.chartHoverFeatureKey
    || Math.abs((point?.x || 0) - (state.chartHoverPoint?.x || 0)) > 8
    || Math.abs((point?.y || 0) - (state.chartHoverPoint?.y || 0)) > 8;
  if (changed) {
    state.chartHoverIndex = idx;
    state.chartHoverFeatureKey = nextFeature;
    state.chartHoverFeatureIndex = target?.index ?? idx;
    state.chartHoverPoint = point;
    drawChart();
    renderDateEvent(idx);
  }
}

function handleChartWheel(event) {
  const all = state.chartAll || [];
  if (all.length < 2) return;
  event.preventDefault();
  const view = chartView();
  const count = view.end - view.start + 1;
  const anchor = chartIndexAtClientX(event.clientX);
  const factor = event.deltaY < 0 ? 0.82 : 1.22;
  let newCount = Math.round(count * factor);
  newCount = Math.max(20, Math.min(all.length, newCount));
  const rel = count > 1 ? (anchor - view.start) / (count - 1) : 0.5;
  let start = Math.round(anchor - rel * (newCount - 1));
  start = Math.max(0, Math.min(start, all.length - newCount));
  state.chartView = { start, end: start + newCount - 1 };
  drawChart();
}

function handleChartMouseDown(event) {
  if (event.button != null && event.button !== 0) return;
  const all = state.chartAll || [];
  if (all.length < 2) return;
  if (state.chartRangeMode || event.shiftKey) {
    event.preventDefault();
    const idx = chartIndexAtClientX(event.clientX);
    state.chartSelectingRange = true;
    state.chartDragging = false;
    state.chartRangeDraft = { start: idx, end: idx };
    state.chartHoverIndex = null;
    if (elements.priceChart) elements.priceChart.style.cursor = "crosshair";
    renderRangeStatsPanel(state.chartRangeDraft);
    drawChart();
    return;
  }
  state.chartDragging = true;
  state.chartDragStartX = event.clientX;
  state.chartDragStartView = chartView();
  if (elements.priceChart) elements.priceChart.style.cursor = "grabbing";
}

function doChartRangeSelect(event) {
  const idx = chartIndexAtClientX(event.clientX);
  const draft = state.chartRangeDraft || { start: idx, end: idx };
  state.chartRangeDraft = { start: draft.start, end: idx };
  state.chartHoverIndex = null;
  renderRangeStatsPanel(state.chartRangeDraft);
  drawChart();
}

function doChartPan(event) {
  const all = state.chartAll || [];
  const canvas = elements.priceChart;
  const layout = chartLayout(canvas);
  const v0 = state.chartDragStartView || chartView();
  const count = v0.end - v0.start + 1;
  const perIdx = layout.innerWidth / Math.max(1, count - 1);
  const shift = Math.round(-(event.clientX - state.chartDragStartX) / perIdx);
  let start = v0.start + shift;
  start = Math.max(0, Math.min(start, all.length - count));
  state.chartView = { start, end: start + count - 1 };
  state.chartHoverIndex = null;
  drawChart();
}

function handleChartMouseUp() {
  if (state.chartSelectingRange) {
    state.chartRangeSelection = normalizeChartRange(
      state.chartRangeDraft?.start,
      state.chartRangeDraft?.end,
    );
    state.chartRangeDraft = null;
    state.chartSelectingRange = false;
    renderRangeStatsPanel(state.chartRangeSelection);
  }
  state.chartDragging = false;
  if (elements.priceChart) elements.priceChart.style.cursor = "crosshair";
  drawChart();
}

function handleChartClick(event) {
  if (!state.chartLargeMode || state.chartRangeMode) return;
  const target = nearestChartFeatureAtPointer(event);
  if (target?.key && target.key !== "candle") {
    showChartLayerExplanation(target.key);
    return;
  }
  const index = target?.index ?? chartIndexAtClientX(event.clientX);
  showChartCandleExplanation(index);
}

function nearestChartFeatureAtPointer(event) {
  const canvas = elements.priceChart;
  if (!canvas || !(state.chartAll || []).length) return null;
  const layout = chartLayout(canvas);
  const point = chartLocalPoint(event);
  const x = point?.x ?? 0;
  const y = point?.y ?? 0;
  const view = chartView();
  const index = chartIndexAtClientX(event.clientX);
  if (x < layout.padding.left || x > layout.width - layout.padding.right) return { key: null, index };
  if (y >= layout.price.top && y <= layout.price.top + layout.price.height) {
    const srLine = (state.chartSRLines || [])
      .map((line) => ({ ...line, distance: Math.abs(y - line.y) }))
      .filter((line) => line.distance <= 9)
      .sort((a, b) => a.distance - b.distance)[0];
    if (srLine) return { key: srLine.key, index };
    const overlays = (state.chartMA || []).filter((series) => indicatorEnabled(series.key));
    let best = { key: "candle", index, distance: Infinity };
    overlays.forEach((series) => {
      const value = series.values?.[index];
      if (value == null || !state._priceYOf) return;
      const distance = Math.abs(y - state._priceYOf(Number(value)));
      if (distance < best.distance) best = { key: series.key, index, distance };
    });
    return best.distance <= 12 ? best : { key: "candle", index };
  }
  if (layout.vol && y >= layout.vol.top && y <= layout.vol.top + layout.vol.height) {
    return { key: "vol", index };
  }
  for (const panel of layout.subplots || []) {
    if (y < panel.top || y > panel.top + panel.height) continue;
    const key = nearestSubplotKey(panel, view, index, y);
    return { key: key || panel.keys.find((item) => indicatorEnabled(item)) || null, index };
  }
  return { key: null, index };
}

function chartLocalPoint(event) {
  const canvas = elements.priceChart;
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  const width = canvas.width ? canvas.width / scale : rect.width;
  const height = canvas.height ? canvas.height / scale : rect.height;
  return {
    x: ((event.clientX - rect.left) / Math.max(1, rect.width)) * width,
    y: ((event.clientY - rect.top) / Math.max(1, rect.height)) * height,
  };
}

function nearestSubplotKey(panel, view, index, y) {
  const enabledKeys = panel.keys.filter((key) => indicatorEnabled(key) && featureSeries(key).some((value) => value != null));
  if (!enabledKeys.length) return null;
  let min = Number.isFinite(panel.min) ? Number(panel.min) : Infinity;
  let max = Number.isFinite(panel.max) ? Number(panel.max) : -Infinity;
  enabledKeys.forEach((key) => {
    const values = featureSeries(key);
    for (let i = view.start; i <= view.end; i += 1) {
      const value = Number(values[i]);
      if (Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  });
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return enabledKeys[0];
  const pad = (max - min) * 0.12 || 1;
  if (!Number.isFinite(panel.min)) min -= pad;
  if (!Number.isFinite(panel.max)) max += pad;
  const yOf = (value) => panel.top + panel.height - ((value - min) / ((max - min) || 1)) * panel.height;
  let best = { key: enabledKeys[0], distance: Infinity };
  enabledKeys.forEach((key) => {
    const value = Number(featureSeries(key)[index]);
    if (!Number.isFinite(value)) return;
    const distance = Math.abs(y - yOf(value));
    if (distance < best.distance) best = { key, distance };
  });
  return best.distance <= 14 ? best.key : enabledKeys[0];
}

function resetChartZoom() {
  const n = (state.chartAll || []).length;
  state.chartView = { start: 0, end: Math.max(0, n - 1) };
  state.chartHoverIndex = null;
  drawChart();
}

function toggleChartRangeMode() {
  state.chartRangeMode = !state.chartRangeMode;
  updateRangeControlState();
  if (elements.priceChart) elements.priceChart.style.cursor = state.chartRangeMode ? "crosshair" : "default";
}

function clearChartRange() {
  state.chartRangeSelection = null;
  state.chartRangeDraft = null;
  state.chartSelectingRange = false;
  renderRangeStatsPanel();
  drawChart();
}

function toggleChartSeries(key) {
  if (!state.chartSeriesHidden) state.chartSeriesHidden = {};
  state.chartSeriesHidden[key] = !state.chartSeriesHidden[key];
  if (key === "vol") {
    state.chartIndicatorEnabled.volume_ma20 = !state.chartSeriesHidden[key];
  } else {
    state.chartIndicatorEnabled[key] = !state.chartSeriesHidden[key];
  }
  state.chartPrefs = { ...normalizeChartPrefs(state.chartPrefs), preset: "custom" };
  renderIndicatorPanel();
  updateChartLegendState();
  if (state.chartLargeMode) showChartLayerExplanation(key, { redraw: false });
  drawChart();
  saveChartPrefsSoon();
}

function updateChartLegendState() {
  const hidden = state.chartSeriesHidden || {};
  document.querySelectorAll("[data-series]").forEach((el) => {
    const key = el.dataset.series;
    const off = state.chartLargeMode
      ? (key === "vol" ? !chartVolumeLayerEnabled() : !indicatorEnabled(key))
      : !!hidden[key];
    el.classList.toggle("legend-off", off);
  });
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
}

function markActiveStock() {
  document.querySelectorAll(".stock-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.stockId === state.activeStockId);
  });
}

function setSyncing(isSyncing) {
  elements.syncButton.disabled = isSyncing;
  elements.quickSyncButton.disabled = isSyncing;
  elements.watchlistButton.disabled = isSyncing;
  elements.syncButton.innerHTML = `${refreshIconMarkup()} ${isSyncing ? "同步中" : "同步"}`;
}

function setScreenerScanning(isScanning) {
  elements.screenerIllustration?.classList.toggle("is-scanning", isScanning);
  elements.screenerStatus?.classList.toggle("is-updating", isScanning);
  elements.screenerSheet?.setAttribute("aria-busy", isScanning ? "true" : "false");
  const radarImage = elements.screenerRadarImage;
  if (radarImage) {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const nextSrc = isScanning && !reduceMotion
      ? radarImage.dataset.scanningSrc
      : radarImage.dataset.idleSrc;
    if (nextSrc && radarImage.getAttribute("src") !== nextSrc) {
      radarImage.setAttribute("src", nextSrc);
    }
  }
  if (elements.refreshScreenerButton) {
    elements.refreshScreenerButton.disabled = isScanning;
    elements.refreshScreenerButton.innerHTML = `${refreshIconMarkup()} ${isScanning ? "更新中" : "更新雷達"}`;
  }
}

async function getJson(url) {
  const response = await fetch(url);
  return readJsonResponse(response);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJsonResponse(response);
}

async function putJson(url, body) {
  const response = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJsonResponse(response);
}

async function patchJson(url, body) {
  const response = await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJsonResponse(response);
}

async function deleteJson(url) {
  const response = await fetch(url, { method: "DELETE" });
  return readJsonResponse(response);
}

async function readJsonResponse(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function showMessage(text, isError = false) {
  elements.message.textContent = text;
  elements.message.classList.toggle("error", isError);
  elements.message.classList.remove("hidden");
}

function hideMessage() {
  elements.message.classList.add("hidden");
}

function stateMessageHTML(kind, title, body, options = {}) {
  const safeKind = ["loading", "empty", "error"].includes(kind) ? kind : "empty";
  const classes = ["state-message", `is-${safeKind}`];
  if (options.compact) classes.push("compact");
  if (options.className) classes.push(options.className);
  const bodyHtml = body ? `<p>${escapeHtml(body)}</p>` : "";
  return `<div class="${classes.join(" ")}"><div><strong>${escapeHtml(title)}</strong>${bodyHtml}</div></div>`;
}

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("zh-TW", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  });
}

function formatApproxPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const number = Number(value);
  let rounded = number;
  if (Math.abs(number) >= 1000) {
    rounded = Math.round(number / 10) * 10;
  } else if (Math.abs(number) >= 100) {
    rounded = Math.round(number);
  } else if (Math.abs(number) >= 10) {
    rounded = Math.round(number * 10) / 10;
  } else {
    rounded = Math.round(number * 100) / 100;
  }
  return `約 ${formatNumber(rounded)}`;
}

function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours > 0) return `${hours} 小時 ${minutes} 分`;
  if (minutes > 0) return `${minutes} 分`;
  return `${totalSeconds} 秒`;
}

function formatInteger(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: 0 });
}

function formatMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toLocaleString("zh-TW", {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  })}`;
}

function formatCompactAmount(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const amount = Number(value);
  const absAmount = Math.abs(amount);
  if (absAmount >= 100000000) return `${formatNumber(amount / 100000000)} 億`;
  if (absAmount >= 10000) return `${formatNumber(amount / 10000)} 萬`;
  return formatInteger(amount);
}

function formatSignedMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "-" : "";
  return `${sign}${Math.abs(number).toLocaleString("zh-TW", {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  })}`;
}

function formatSignedNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "-" : "";
  return `${sign}${Math.abs(number).toLocaleString("zh-TW", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })}`;
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${Number(value).toLocaleString("zh-TW", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })}%`;
}

function formatPlainPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toLocaleString("zh-TW", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })}%`;
}

function formatRevenue(value) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return `${(Number(value) / 100000).toLocaleString("zh-TW", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })} 億元`;
}

function setTone(element, value) {
  element.classList.toggle("up", Number(value) > 0);
  element.classList.toggle("down", Number(value) < 0);
}

function toneClass(value) {
  if (Number(value) > 0) return "up";
  if (Number(value) < 0) return "down";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toneLabel(tone) {
  if (tone === "positive") return "相對穩";
  if (tone === "caution") return "留意";
  if (tone === "unknown") return "待補資料";
  return "觀察";
}

function valuationStateLabel(state) {
  if (state === "applicable") return "股利法適用";
  if (state === "low_confidence") return "股利法參考性低";
  if (state === "not_applicable") return "股利法不適合";
  return "股利法待判斷";
}

function refreshIconMarkup() {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 0 1-15.4 6.4M3 12A9 9 0 0 1 18.4 5.6M18 2v4h-4M6 22v-4h4"/></svg>`;
}

function starIconMarkup() {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 14.7 9l6 .9-4.3 4.2 1 6-5.4-2.9L6.6 20l1-6L3.3 9.9l6-.9L12 3.5Z"/></svg>`;
}
// UI 重整版本標記

// ---- 法人籌碼（三大法人）卡片與雷達籌碼面 ----
function formatLots(shares) {
  if (shares == null || Number.isNaN(Number(shares))) return "--";
  const lots = Math.round(Number(shares) / 1000);
  const sign = lots > 0 ? "+" : "";
  return `${sign}${lots.toLocaleString("zh-TW")}`;
}

function chipsLevelTone(level) {
  if (level === "警戒") return "high";
  if (level === "注意") return "mid";
  if (level === "留意") return "low";
  return "calm";
}

function chipsRadarBody(chips) {
  if (!chips || !chips.available) return "尚未同步三大法人買賣超（按『同步』後顯示）。";
  const parts = [];
  if (chips.consecutive_total_sell_days >= 1) {
    parts.push(`三大法人連續 ${chips.consecutive_total_sell_days} 天賣超`);
  } else {
    parts.push("三大法人最新一日未連續賣超");
  }
  const sum = chips.sum_20 ? chips.sum_20.total_net : null;
  if (sum != null) {
    const word = sum < 0 ? "淨賣超" : sum > 0 ? "淨買超" : "持平";
    parts.push(`近${chips.sum_20.days}日合計${word} ${formatLots(Math.abs(sum))} 張`);
  }
  return `${parts.join("，")}。`;
}

function renderChipsCard(chips) {
  const el = elements.chipsCard;
  if (!el) return;
  if (!chips || !chips.available) {
    el.className = "chips-card chips-empty";
    el.innerHTML = stateMessageHTML("empty", "等待法人資料", (chips && chips.headline) || "按「讀取三大法人」後，這裡會顯示近 20 日買賣超。", {
      compact: true,
      className: "chips-empty-text",
    });
    return;
  }
  const tone = chipsLevelTone(chips.level);
  const latest = chips.latest || {};
  const rows = [
    ["外資", latest.foreign_net],
    ["投信", latest.trust_net],
    ["自營商", latest.dealer_net],
    ["三大法人", latest.total_net],
  ];
  const cells = rows.map(([label, v]) => {
    const dir = Number(v) > 0 ? "買超" : Number(v) < 0 ? "賣超" : "持平";
    return `<div class="chips-cell"><span>${label}</span><strong>${formatLots(v)}</strong><em>張・${dir}</em></div>`;
  }).join("");
  const reasons = (chips.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  const analysisItems = (chips.analysis || []).map((a) => `<li>${escapeHtml(a)}</li>`).join("");
  const analysisBlock = analysisItems
    ? `<div class="chips-analysis"><div class="chips-analysis-title">可能的解讀</div><ul>${analysisItems}</ul><p class="chips-analysis-note">${escapeHtml(chips.analysis_note || "")}</p></div>`
    : "";
  el.className = `chips-card chips-${tone}`;
  el.innerHTML = `
    <div class="chips-head">
      <span class="chips-badge chips-${tone}">籌碼面 ${escapeHtml(chips.level)}</span>
      <span class="chips-asof">資料日 ${escapeHtml(chips.as_of || "--")}</span>
    </div>
    <p class="chips-headline">${escapeHtml(chips.headline || "")}</p>
    <div class="chips-grid">${cells}</div>
    <div class="chips-trend">
      <div class="chips-trend-label">近 ${(chips.trend || []).length} 日三大法人買賣超（上=買超，下=賣超）</div>
      <canvas id="chipsSparkline" width="520" height="64"></canvas>
    </div>
    ${reasons ? `<ul class="chips-reasons">${reasons}</ul>` : ""}
    ${analysisBlock}
    <p class="disclaimer">${escapeHtml(chips.disclaimer || "")}</p>
  `;
  drawChipsSparkline(document.getElementById("chipsSparkline"), chips.trend || []);
}

function drawChipsSparkline(canvas, trend) {
  if (!canvas || !canvas.getContext) return;
  const rect = canvas.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  const w = Math.max(320, Math.floor((rect.width || 520) * scale));
  const h = Math.floor(64 * scale);
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const width = w / scale;
  const height = h / scale;
  const colors = chartThemeColors();
  ctx.clearRect(0, 0, width, height);
  const vals = (trend || []).map((t) => Number(t.value) || 0);
  if (!vals.length) return;
  const maxAbs = Math.max(1, ...vals.map((v) => Math.abs(v)));
  const mid = height / 2;
  const n = vals.length;
  const slot = width / n;
  const bw = Math.max(2, slot * 0.62);
  ctx.strokeStyle = colors.line;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, mid);
  ctx.lineTo(width, mid);
  ctx.stroke();
  vals.forEach((v, i) => {
    const x = slot * i + slot / 2;
    const barH = (Math.abs(v) / maxAbs) * (mid - 5);
    ctx.fillStyle = v >= 0 ? colors.brand : colors.warn;
    if (v >= 0) ctx.fillRect(x - bw / 2, mid - barH, bw, barH);
    else ctx.fillRect(x - bw / 2, mid, bw, barH);
  });
}

// ---- 三大法人獨立讀取 + 體質總評 ----
async function loadInstitutional() {
  const stockId = state.activeStockId;
  if (!stockId) return;
  const btn = elements.loadChipsButton || document.getElementById("loadChipsButton");
  if (btn) { btn.disabled = true; btn.textContent = "讀取中…第一次較久"; }
  try {
    const payload = await postJson("/api/institutional/sync", { stock_id: stockId });
    if (state.activeStockId !== stockId) return;
    state.activeChips = payload.chips || null;
    renderChipsCard(payload.chips);
    state.activeAssessment = payload.assessment;
    renderAssessmentMerged();
    const chipsMap = {};
    (payload.chips_series || []).forEach((c) => { if (c && c.date) chipsMap[c.date] = c; });
    state.chartChips = chipsMap;
    drawChart();
  } catch (error) {
    showMessage(`讀取三大法人失敗：${error.message}`, true);
  } finally {
    if (btn && state.activeStockId === stockId) { btn.disabled = false; btn.textContent = "讀取三大法人（近一年）"; }
  }
}

function assessTone(lean) {
  if (lean === "偏多解讀") return "bull";
  if (lean === "偏空解讀") return "bear";
  return "neutral";
}

function assessmentGrade(counts) {
  const net = (Number(counts.bull) || 0) - (Number(counts.bear) || 0);
  if (net >= 2) return { label: "體質偏強", tone: "bull" };
  if (net <= -2) return { label: "體質偏弱", tone: "bear" };
  return { label: "體質中性", tone: "neutral" };
}

function assessmentConclusion(factors, grade) {
  const bull = factors.filter((f) => f.lean === "偏多解讀").map((f) => f.label);
  const bear = factors.filter((f) => f.lean === "偏空解讀").map((f) => f.label);
  let s = `綜合 ${factors.length} 個面向，目前「${grade.label}」`;
  if (bull.length) s += `；偏多的是 ${bull.join("、")}`;
  if (bear.length) s += `；偏空的是 ${bear.join("、")}`;
  if (!bull.length && !bear.length) s += "；各面向多為中性";
  return `${s}。這是傳統解讀的清點，不是預測，也不是買賣建議。`;
}

function assessmentChecklist(factors) {
  const out = [];
  const bear = factors.filter((f) => f.lean === "偏空解讀").map((f) => f.label);
  if (bear.length) out.push(`先弄懂為什麼這幾項偏空：${bear.join("、")}`);
  out.push("營收／獲利趨勢有沒有站穩？（看下方營收、財報）");
  out.push("最近有沒有地雷風險新聞？（看消息面／地雷雷達）");
  out.push("三大法人最近偏買還偏賣？（按法人卡的「讀取三大法人」）");
  out.push("你能接受的最大虧損是多少？停損點想好了嗎？");
  return out;
}

function renderAssessment(a) {
  const el = elements.assessmentCard;
  if (!el) return;
  if (!a || !a.available) {
    el.className = "assess-card assess-empty";
    el.innerHTML = stateMessageHTML("empty", "等待體質總評", (a && a.summary) || "日線資料不足，先同步後再看體質總評。", {
      compact: true,
      className: "assess-empty-text",
    });
    return;
  }
  const counts = a.counts || {};
  const factorsArr = a.factors || [];
  const grade = assessmentGrade(counts);
  const conclusion = assessmentConclusion(factorsArr, grade);
  const checklist = assessmentChecklist(factorsArr);
  const factorRows = factorsArr.map((f) => `
    <details class="assess-factor assess-${f.tone}">
      <summary>
        <span class="assess-dot assess-${f.tone}"></span>
        <span class="assess-flabel">${escapeHtml(f.label)}</span>
        <span class="assess-lean assess-${f.tone}">${escapeHtml(f.lean)}</span>
      </summary>
      <div class="assess-detail">
        <p class="assess-reading">${escapeHtml(f.reading)}${f.value ? `（${escapeHtml(String(f.value))}）` : ""}</p>
        <p class="assess-trad">${escapeHtml(f.traditional || "")}</p>
        ${INDICATOR_GUIDES[f.key] ? `<button type="button" class="guide-link" onclick="openIndicatorGuide('${f.key}')">📖 怎麼看「${escapeHtml(f.label)}」？</button>` : ""}
      </div>
    </details>`).join("");
  el.className = "assess-card";
  el.innerHTML = `
    <div class="assess-grade assess-grade-${grade.tone}">
      <div class="assess-grade-badge">${escapeHtml(grade.label)}</div>
      <div class="assess-grade-meta">
        <div class="assess-tally">
          <span class="assess-pill assess-bull">偏多 ${counts.bull || 0}</span>
          <span class="assess-pill assess-bear">偏空 ${counts.bear || 0}</span>
          <span class="assess-pill assess-neutral">中性 ${counts.neutral || 0}</span>
        </div>
        <p class="assess-conclusion">${escapeHtml(conclusion)}</p>
      </div>
    </div>
    <details class="assess-factors-wrap">
      <summary>看 ${factorsArr.length} 項因子細節</summary>
      <div class="assess-factors">${factorRows}</div>
    </details>
    <div class="assess-checklist">
      <div class="assess-checklist-title">決定前，先問自己</div>
      <ul>${checklist.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>
    </div>
    <p class="disclaimer">${escapeHtml(a.disclaimer || "")}</p>
  `;
}

// ---- 支撐/壓力參考線（近60日高低） ----
// 三種週期的支撐/壓力（swing pivot）；可由圖例個別開關
const SR_TIMEFRAMES = [
  { key: "sr_s", label: "短", window: 20, k: 2, color: "#2C5475" },
  { key: "sr_m", label: "波", window: 60, k: 3, color: "#B0820B" },
  { key: "sr_l", label: "長", window: 240, k: 5, color: "#6B4FA0" },
];

function findSwingPivots(bars, k) {
  const highs = [];
  const lows = [];
  for (let i = k; i < bars.length - k; i += 1) {
    const h = Number(bars[i].high);
    const l = Number(bars[i].low);
    if (!Number.isFinite(h) || !Number.isFinite(l)) continue;
    let isHigh = true;
    let isLow = true;
    for (let j = i - k; j <= i + k; j += 1) {
      if (j === i) continue;
      if (Number(bars[j].high) >= h) isHigh = false;
      if (Number(bars[j].low) <= l) isLow = false;
    }
    if (isHigh) highs.push({ index: i, value: h });
    if (isLow) lows.push({ index: i, value: l });
  }
  return { highs, lows };
}

function pickResistance(pivotHighs, seg, close) {
  const above = pivotHighs.filter((p) => p.value > close);
  if (above.length) return above.reduce((best, item) => item.value < best.value ? item : best, above[0]);
  if (pivotHighs.length) return pivotHighs.reduce((best, item) => item.value > best.value ? item : best, pivotHighs[0]);
  let best = null;
  seg.forEach((p, index) => {
    const value = Number(p.high);
    if (Number.isFinite(value) && (!best || value > best.value)) best = { index, value };
  });
  return best;
}

function pickSupport(pivotLows, seg, close) {
  const below = pivotLows.filter((p) => p.value < close);
  if (below.length) return below.reduce((best, item) => item.value > best.value ? item : best, below[0]);
  if (pivotLows.length) return pivotLows.reduce((best, item) => item.value < best.value ? item : best, pivotLows[0]);
  let best = null;
  seg.forEach((p, index) => {
    const value = Number(p.low);
    if (Number.isFinite(value) && (!best || value < best.value)) best = { index, value };
  });
  return best;
}

function drawSupportResistance(ctx, layout, view) {
  const yOf = state._priceYOf;
  const all = state.chartAll || [];
  if (!yOf || all.length < 10) return;
  const hidden = state.chartSeriesHidden || {};
  const c = Number(all[all.length - 1].close);
  const provisional = isIntradayOverlayActive();
  const top = layout.price.top;
  const bot = layout.price.top + layout.price.height;
  state.chartSRLines = [];
  ctx.save();
  ctx.lineWidth = 1;
  ctx.font = "10.5px Microsoft JhengHei, Segoe UI, Arial";
  SR_TIMEFRAMES.forEach((tf) => {
    if (hidden[tf.key]) return;
    const windowSize = Math.min(tf.window, all.length);
    const startIndex = all.length - windowSize;
    const seg = all.slice(startIndex);
    const piv = findSwingPivots(seg, tf.k);
    const resistance = pickResistance(piv.highs, seg, c);
    const support = pickSupport(piv.lows, seg, c);
    const prefix = provisional ? "暫算" : "";
    [[`${prefix}${tf.label}壓`, resistance, "壓力"], [`${prefix}${tf.label}撐`, support, "支撐"]].forEach(([label, level, kindLabel]) => {
      const price = Number(level?.value);
      if (!Number.isFinite(price)) return;
      const y = yOf(price);
      if (y < top || y > bot) return;
      const globalIndex = startIndex + Number(level.index || 0);
      const hoverKey = `${tf.key}_${kindLabel === "壓力" ? "res" : "sup"}`;
      const line = { key: hoverKey, timeframeKey: tf.key, label, price, y, window: windowSize, startIndex, pivotIndex: globalIndex, color: tf.color, kindLabel, provisional };
      state.chartSRLines.push(line);
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = tf.color;
      const emphasis = activeChartEmphasisFeature();
      ctx.globalAlpha = emphasis && emphasis !== hoverKey && emphasis !== tf.key ? .3 : 1;
      ctx.lineWidth = emphasis === hoverKey || emphasis === tf.key ? 1.8 : 1;
      ctx.beginPath();
      const startX = globalIndex >= view.start && startIndex <= view.end
        ? chartXOf(Math.max(view.start, startIndex), view, layout)
        : layout.padding.left;
      ctx.moveTo(startX, y);
      ctx.lineTo(layout.width - layout.padding.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = tf.color;
      ctx.globalAlpha = 1;
      ctx.fillText(`${label} ${formatNumber(price)} · 近${windowSize}日${provisional ? " · 盤中" : ""}`, layout.padding.left + 4, y - 3);
      if (globalIndex >= view.start && globalIndex <= view.end) {
        const px = chartXOf(globalIndex, view, layout);
        ctx.beginPath();
        ctx.arc(px, y, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    });
  });
  ctx.restore();
}

function findSupportResistanceLine(key) {
  const lines = Array.isArray(state.chartSRLines) ? state.chartSRLines : [];
  return lines.find((item) => item.key === key || item.timeframeKey === key) || null;
}

// ---- 體質總評併入消息面（地雷雷達） ----
function newsFactorFromRisk(rs) {
  if (!rs || !rs.level) return null;
  const level = rs.level;
  const reasons = rs.reasons && rs.reasons.length ? rs.reasons.join(" ") : "";
  let lean, tone, reading;
  if (level === "警戒" || level === "注意") {
    lean = "偏空解讀"; tone = "bear";
    reading = `消息面${level}：${reasons || "近期新聞出現需留意的風險字眼"}`;
  } else if (level === "留意") {
    lean = "中性"; tone = "neutral";
    reading = `消息面留意：${reasons || "近期新聞有少量風險字眼"}`;
  } else {
    lean = "中性"; tone = "neutral";
    reading = "近期新聞未偵測到明顯風險字眼，消息面暫時平靜。";
  }
  return {
    key: "news", label: "消息面（地雷雷達）", reading, lean, tone, value: level,
    traditional: "退場、財務危機、交易限制等屬於重大風險事件，傳統上被視為利空；沒有風險字眼則消息面暫時平靜。新聞只涵蓋近期。",
  };
}

function recountAssessment(factors) {
  const bull = factors.filter((f) => f.lean === "偏多解讀").length;
  const bear = factors.filter((f) => f.lean === "偏空解讀").length;
  const neutral = factors.length - bull - bear;
  const tilt = bull > bear ? "目前以『偏多解讀』的因子居多"
    : bear > bull ? "目前以『偏空解讀』的因子居多"
    : "目前多空解讀的因子大致均衡";
  const summary = `綜合 ${factors.length} 個面向：傳統上偏多解讀 ${bull} 項、偏空解讀 ${bear} 項、中性 ${neutral} 項，${tilt}。這只是把各面向的傳統解讀做個清點，不是預測，也不是買賣建議。`;
  return { bull, bear, neutral, summary };
}

function renderAssessmentMerged() {
  const base = state.activeAssessment;
  if (!base || !base.available) { renderAssessment(base); return; }
  const factors = base.factors.slice();
  const nf = newsFactorFromRisk(state.newsRiskSummary);
  if (nf) factors.push(nf);
  const c = recountAssessment(factors);
  renderAssessment({
    available: true,
    counts: { bull: c.bull, bear: c.bear, neutral: c.neutral },
    summary: c.summary,
    factors,
    disclaimer: base.disclaimer,
  });
}

// ---- 指標教學庫（怎麼看），點體質總評因子的「怎麼看」會跳出 ----
const INDICATOR_GUIDES = {
  rsi: {
    title: "RSI 相對強弱指標",
    intro: "衡量一段期間內價格『漲勢』與『跌勢』力道的指標，數值 0–100。越高代表買方越強，越低代表賣方越強。本 App 用 14 日 Wilder RSI。",
    points: [
      { h: "50 多空分水嶺", b: "大於 50 代表多方（買方）力道較強、偏強格局；小於 50 偏弱格局。" },
      { h: "70 / 30 過熱過冷", b: "大於等於 70 為超買（漲多過熱，傳統上隨時有拉回風險）；小於等於 30 為超賣（跌深，傳統上有反彈機會）。" },
      { h: "黃金 / 死亡交叉", b: "短天期 RSI 向上穿過長天期＝買盤回流（偏多訊號）；向下跌破＝賣壓湧現（偏空訊號）。" },
      { h: "背離（判斷反轉）", b: "股價越跌越低、RSI 卻越來越高＝底背離，跌勢減弱可能反轉向上；股價越漲越高、RSI 卻越來越低＝頂背離，漲勢衰退可能反轉向下。" },
    ],
    note: "技術面僅供參考，不預測股價、不構成買賣建議；市場常常不照技術面走。",
  },
  kd: {
    title: "KD 隨機指標 (Stochastic)",
    intro: "用近 9 日的最高、最低與收盤，算出 K 與 D 兩條線（0–100），反映收盤落在區間的相對高低與短期動能。本 App 用 9,3,3。",
    points: [
      { h: "80 / 20 過熱過冷", b: "K 大於 80 為高檔超買（傳統上易回或鈍化）；K 小於 20 為低檔超賣（傳統上易彈）。" },
      { h: "黃金 / 死亡交叉", b: "K 由下往上穿過 D＝黃金交叉（偏多）；K 由上往下跌破 D＝死亡交叉（偏空）。" },
      { h: "高 / 低檔鈍化", b: "強勢時 K、D 可能長時間黏在 80 以上（高檔鈍化）續強；弱勢時黏在 20 以下續弱。" },
    ],
    note: "技術面僅供參考，不預測股價、不構成買賣建議。",
  },
  bias: {
    title: "乖離率 BIAS（對月線）",
    intro: "收盤價偏離均線（這裡用 20 日月線）的百分比，看股價拉離平均成本多遠。",
    points: [
      { h: "正乖離過大", b: "股價遠高於均線、漲多，傳統上容易回測均線（不保證）。" },
      { h: "負乖離過大", b: "股價遠低於均線、跌深，傳統上容易出現反彈。" },
      { h: "貼近均線", b: "乖離小，價格在平均成本附近、較無極端。" },
      { h: "沒有固定門檻", b: "每檔波動不同，乖離『多大算大』要看自己歷史；本 App 以 ±8% 溫和、±15% 偏大當參考。" },
    ],
    note: "只描述目前讀數，不預測股價、不構成買賣建議。",
  },
  ma: {
    title: "均線 MA（5 / 20 / 60）",
    intro: "近 N 日的平均收盤：MA5 週線、MA20 月線、MA60 季線，用來看趨勢方向與平均成本。",
    points: [
      { h: "多頭排列", b: "MA5 大於 MA20 大於 MA60 且股價在上，短中長期都向上，傳統上偏多。" },
      { h: "空頭排列", b: "MA5 小於 MA20 小於 MA60 且股價在下，傳統上偏弱。" },
      { h: "均線糾結", b: "三條均線交錯黏在一起，方向不明、常是盤整。" },
      { h: "動態支撐 / 壓力", b: "上升時均線常被當支撐，下跌時常被當壓力。" },
      { h: "資料不足時", b: "未滿 N 根日線就不畫該條均線；剛上市或只同步少量資料時，MA60 可能暫時空白。" },
    ],
    note: "趨勢工具，不預測股價、不構成買賣建議。",
  },
  volume: {
    title: "量能（量比）",
    intro: "當日成交量 ÷ 近 20 日均量，看今天交投比平常熱還是冷。",
    points: [
      { h: "爆量（約 1.8 倍以上）", b: "成交量明顯放大。配合上漲＝買盤積極；配合下跌＝賣壓宣洩，要和價格方向一起看。" },
      { h: "量縮（約 0.6 倍以下）", b: "交投清淡、觀望氣氛濃。" },
      { h: "量先價行", b: "傳統上成交量常領先價格，轉折前後量常先變化。" },
      { h: "單看量不分多空", b: "量大不一定是好或壞，關鍵看價格往哪走。" },
    ],
    note: "只描述目前讀數，不預測股價、不構成買賣建議。",
  },
  position: {
    title: "價格位階（近一年）",
    intro: "目前收盤落在近一年最高與最低之間的相對位置（百分位）。",
    points: [
      { h: "高位階（80% 以上）", b: "接近近一年高點，追高風險較大（不代表會回）。" },
      { h: "低位階（20% 以下）", b: "接近近一年低點、相對抗跌，但弱勢股也可能再破底。" },
      { h: "中段", b: "落在區間中間，較無極端。" },
    ],
    note: "只描述相對位置，不預測股價、不構成買賣建議。",
  },
  candle: {
    title: "K 線（蠟燭圖）",
    intro: "每根 K 棒代表一天：紅色＝收盤高於開盤（收漲），綠色＝收盤低於開盤（收跌）。",
    points: [
      { h: "實體與影線", b: "中間粗體＝開盤到收盤的範圍；上下細線（影線）＝當天最高與最低價。" },
      { h: "長紅 / 長黑", b: "實體很長代表當天買方（紅）或賣方（綠）力道強勁。" },
      { h: "上下影線", b: "長下影＝低點有買盤承接；長上影＝高點有賣壓出現。" },
      { h: "十字線", b: "開盤約等於收盤、實體很小，多空拉鋸、方向猶豫，常出現在轉折附近。" },
    ],
    note: "K 線只是把每天價格畫出來幫你看趨勢，不預測股價、不構成買賣建議。",
  },
  sr: {
    title: "支撐 / 壓力",
    intro: "支撐＝地板（跌到這裡常有人接、止跌）；壓力＝天花板（漲到這裡常有人賣、卡住）。本 App 取近期波段轉折點中最接近現價的上方壓力與下方支撐。",
    points: [
      { h: "為什麼會形成", b: "那個價位之前大量成交過，套牢、停利、停損的人都集中在附近，價格回到那裡就湧出買盤或賣壓。" },
      { h: "突破與跌破（角色互換）", b: "壓力被突破後常變成支撐；支撐被跌破後常變成壓力。" },
      { h: "時間尺要配交易長度", b: "短線看近 20 日、波段看近 60 日、長線看近一年；本 App 三種都可由圖例個別開關。" },
      { h: "是區帶、不是精準價", b: "它是『很多人會有反應的價帶』，而且會被突破，不是會反彈或回跌的保證。" },
    ],
    note: "只描述價位參考，不預測股價、不構成買賣建議。",
  },
  range: {
    title: "區間統計",
    intro: "把你框選的一段 K 線整理成已發生的價量統計，方便比較不同時間段的波動與量能。",
    points: [
      { h: "期間漲跌幅", b: "用區間最後一天收盤和第一天收盤比較，只描述這段期間已發生的價格變化。" },
      { h: "振幅", b: "區間最高價減最低價，再除以起始收盤價；數字越大，代表這段期間上下震盪越寬。" },
      { h: "年化波動度", b: "用區間內每日收盤報酬的標準差換算成年化尺度，樣本短時容易不穩。" },
      { h: "VWAP", b: "用成交量加權後的平均價格；若資料沒有成交金額，系統用收盤價與成交量近似。" },
    ],
    note: "區間統計只整理歷史資料，不預測股價、不構成買賣建議。",
  },
  chips: {
    title: "三大法人（籌碼）",
    intro: "三大法人＝外資、投信（國內基金）、自營商（券商自有部位）。買賣超＝當天買進減賣出的張數，正值買超、負值賣超。",
    points: [
      { h: "誰的錢", b: "外資資金大、偏快錢；投信偏中長線的本土法人；自營商偏短線與避險，單日波動大。" },
      { h: "連續性比單日重要", b: "連續多天同方向，比單一天更能看出態度；單日大買大賣可能只是調節。" },
      { h: "同步 vs 分歧", b: "三大法人同步買或同步賣＝共識較強；外資賣、投信買＝看法分歧、沒有一面倒。" },
      { h: "賣壓是否加速", b: "近 3 日賣超明顯大於近 20 日平均，代表賣壓在加速，值得多留意。" },
    ],
    note: "法人也可能因避險、調節、換股而進出，不代表股價方向，也不是買賣建議。",
  },
  risk: {
    title: "地雷雷達",
    intro: "把近期新聞裡的『風險字眼』抓出來，配上籌碼與價量，整理成消息面／籌碼面／價量面三行提醒。",
    points: [
      { h: "抓哪些風險", b: "終止上市、變更交易方法、淨值轉負、暫停交易、財務危機、訴訟裁罰等重大風險事件。" },
      { h: "等級", b: "由低到高：留意 → 注意 → 警戒；出現退場、財務危機這類關鍵風險會直接升到警戒。" },
      { h: "看到警戒怎麼辦", b: "別只看雷達，自己再去公開資訊觀測站、重大訊息查證，確認是不是真的踩到地雷。" },
      { h: "限制", b: "新聞只涵蓋最近約 45 天，且是關鍵字粗略歸類，可能漏抓或誤判。" },
    ],
    note: "只幫你快速察覺風險，不預測股價、不構成買賣建議。",
  },
};

function openIndicatorGuide(key) {
  const g = INDICATOR_GUIDES[key];
  if (!g || !elements.glossaryOverlay) return;
  elements.glossaryTitle.textContent = g.title;
  elements.glossaryPlain.textContent = g.intro || "";
  if (elements.glossaryHow) elements.glossaryHow.textContent = "";
  if (elements.glossaryGuide) {
    const pts = (g.points || []).map((p) =>
      `<div class="guide-point"><div class="guide-point-h">${escapeHtml(p.h)}</div><div class="guide-point-b">${escapeHtml(p.b)}</div></div>`
    ).join("");
    elements.glossaryGuide.innerHTML = pts + (g.note ? `<p class="guide-note">${escapeHtml(g.note)}</p>` : "");
    elements.glossaryGuide.classList.remove("hidden");
  }
  elements.glossaryOverlay.classList.remove("hidden");
  elements.glossaryOverlay.setAttribute("aria-hidden", "false");
  if (elements.glossaryClose) elements.glossaryClose.focus();
}

function srBadge(item) {
  const sr = item.sr;
  if (!sr || !sr.available) return "";
  let badge = "";
  if (sr.status === "接近波撐") badge = `<span class="sr-badge sr-support">接近波撐 ${formatNumber(sr.support)}</span>`;
  else if (sr.status === "接近波壓") badge = `<span class="sr-badge sr-resist">接近波壓 ${formatNumber(sr.resistance)}</span>`;
  else return "";
  return badge + srDateTag(sr.as_of);
}

function srDateTag(asOf) {
  if (!asOf) return "";
  const d = new Date(asOf);
  if (Number.isNaN(d.getTime())) return "";
  const days = Math.round((Date.now() - d.getTime()) / 86400000);
  const stale = days > 7;
  const label = stale ? `資料 ${asOf}・過期 ${days} 天` : `資料 ${asOf}`;
  return `<span class="sr-date${stale ? " stale" : ""}">${escapeHtml(label)}</span>`;
}

// ---- 全市場資料下載：控制 + 輪詢 ----
async function bulkStart() {
  try { renderBulk(await postJson("/api/bulk-download/start", {})); startBulkPolling(); }
  catch (e) { showMessage(`無法開始下載：${e.message}`, true); }
}
async function bulkPause() {
  try { renderBulk(await postJson("/api/bulk-download/pause", {})); } catch (e) { showMessage(e.message, true); }
}
async function bulkResume() {
  try { renderBulk(await postJson("/api/bulk-download/resume", {})); startBulkPolling(); } catch (e) { showMessage(e.message, true); }
}
async function bulkRetryFailed() {
  try { renderBulk(await postJson("/api/bulk-download/retry-failed", {})); startBulkPolling(); }
  catch (e) { showMessage(e.message, true); }
}
async function bulkStop() {
  try { renderBulk(await postJson("/api/bulk-download/stop", {})); } catch (e) { showMessage(e.message, true); }
}
function startBulkPolling() {
  if (state.bulkTimer) return;
  state.bulkTimer = window.setInterval(async () => {
    try {
      const st = await getJson("/api/bulk-download/status");
      renderBulk(st);
      if (!st.running) { window.clearInterval(state.bulkTimer); state.bulkTimer = null; }
    } catch (e) { /* 暫時讀不到狀態，下次再試 */ }
  }, 2000);
}
function renderBulk(st) {
  if (!st) return;
  const wrap = document.getElementById("bulkProgressWrap");
  const bar = document.getElementById("bulkBar");
  const txt = document.getElementById("bulkStatusText");
  const startBtn = document.getElementById("bulkStartBtn");
  const pauseBtn = document.getElementById("bulkPauseBtn");
  const resumeBtn = document.getElementById("bulkResumeBtn");
  const retryBtn = document.getElementById("bulkRetryFailedBtn");
  const stopBtn = document.getElementById("bulkStopBtn");
  if (!wrap) return;
  const active = Boolean(st.running);
  const failedCount = Number(st.failed_count || 0);
  wrap.classList.toggle("hidden", st.status === "idle");
  if (bar) {
    const pct = st.total ? Math.round((Number(st.done) / Number(st.total)) * 100) : (st.status === "preparing" ? 5 : 0);
    bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  }
  if (txt) {
    const map = { idle: "尚未開始", preparing: "準備中（抓全市場共用資料）…", running: "下載中", paused: "已暫停", stopped: "已停止", done: "完成", error: "發生錯誤" };
    let s = map[st.status] || st.status || "";
    if (st.retry_failed_only) s += "（只重試失敗）";
    if (st.total) s += `　${st.done}/${st.total}`;
    if (st.current) s += `　目前：${st.current}`;
    if (st.eta_seconds != null) s += `　ETA ${formatDuration(st.eta_seconds)}`;
    if (st.skipped) s += `　已跳過 ${st.skipped}`;
    if (failedCount) s += `　失敗 ${failedCount}`;
    if (st.message) s += `　${st.message}`;
    txt.textContent = s;
  }
  if (startBtn) startBtn.disabled = active || st.status === "preparing";
  if (pauseBtn) pauseBtn.disabled = !active || Boolean(st.paused);
  if (resumeBtn) resumeBtn.disabled = !(active && st.paused);
  if (retryBtn) retryBtn.disabled = active || failedCount === 0;
  if (stopBtn) stopBtn.disabled = !active;
}
(async function bulkInit() {
  try {
    const st = await getJson("/api/bulk-download/status");
    renderBulk(st);
    if (st.running) startBulkPolling();
  } catch (e) { /* 伺服器尚未就緒，略過 */ }
})();

// ---- 本地資料盤點 + 波段關卡提醒 ----
async function loadLocalData() {
  try {
    const payload = await getJson("/api/local-data");
    state.localData = payload;
    renderLevelsRadar(payload);
    renderLocalDataTable(payload);
  } catch (e) {
    renderLocalDataError(e);
  }
}

function renderLocalDataError(error) {
  if (elements.localDataSummary) {
    elements.localDataSummary.textContent = "本地資料讀取失敗；可能是資料庫忙碌或後端暫時沒有回應。";
  }
  if (elements.localDataRows) {
    elements.localDataRows.innerHTML = `<tr><td colspan="7">${stateMessageHTML("error", "讀取失敗", error.message || "請稍後重新整理。", { compact: true })}</td></tr>`;
  }
  if (elements.levelsRadarList) {
    elements.levelsRadarList.innerHTML = stateMessageHTML("error", "波段提醒暫時不可用", error.message || "請稍後重新整理。", { compact: true });
  }
}

function renderLevelsRadar(payload) {
  const el = elements.levelsRadarList;
  if (!el) return;
  const near = (payload && payload.near) || [];
  state.levelTargets = uniqueStockIds(near.map((item) => item.stock_id)).slice(0, 20);
  updateLevelsSyncControls();
  if (!near.length) {
    el.innerHTML = stateMessageHTML("empty", "目前沒有接近關卡", "同步個股、或在雷達中心完成全市場下載後，這裡會列出接近波撐/波壓的股票。", {
      compact: true,
      className: "levels-empty",
    });
    return;
  }
  el.innerHTML = near.map((it) => {
    const isSup = it.sr_status === "接近波撐";
    const cls = isSup ? "sr-support" : "sr-resist";
    const level = isSup ? `波撐 ${formatNumber(it.support)}` : `波壓 ${formatNumber(it.resistance)}`;
    const stale = it.stale_days > 7
      ? `<span class="sr-date stale">過期 ${it.stale_days} 天</span>`
      : `<span class="sr-date">資料 ${escapeHtml(it.last_date)}</span>`;
    return `<div class="levels-row" data-level-row="${escapeHtml(it.stock_id)}">
      <span class="levels-name"><strong>${escapeHtml(it.stock_id)} ${escapeHtml(it.name || "")}</strong></span>
      <span class="sr-badge ${cls}">${escapeHtml(it.sr_status)}・${level}</span>
      ${stale}
      <span class="levels-row-actions">
        <button class="table-action level-sync-action" type="button" data-level-sync-stock="${escapeHtml(it.stock_id)}">${refreshIconMarkup()} 更新</button>
        <button class="table-action" type="button" data-screener-stock="${escapeHtml(it.stock_id)}">看個股</button>
      </span>
    </div>`;
  }).join("");
}

async function syncLevelsTargets() {
  if (state.levelsSyncing) return;
  const targets = uniqueStockIds(state.levelTargets || []);
  if (!targets.length) {
    showMessage("目前沒有可更新的波段提醒目標。", true);
    return;
  }
  state.levelsSyncing = true;
  updateLevelsSyncControls({ text: `更新中 0/${targets.length}` });
  showMessage(`開始更新 ${targets.length} 檔波段提醒資料...`);
  try {
    const payload = await syncTargetsBatch(targets);
    const succeeded = Number(payload.succeeded || 0);
    const failed = Number(payload.failed || 0);
    const skipped = Number(payload.skipped || 0);
    const refreshed = Math.max(0, succeeded - skipped);
    const message = failed
      ? `波段提醒資料更新完成：${succeeded}/${payload.requested || targets.length} 檔成功，${failed} 檔失敗。`
      : skipped
        ? `波段提醒資料檢查完成：${refreshed} 檔更新、${skipped} 檔已是最近收盤。`
        : `波段提醒資料更新完成：${succeeded} 檔已更新。`;
    showMessage(message, failed > 0);
    await loadLocalData();
    if (state.activeStockId && targets.includes(state.activeStockId)) {
      await loadStock(state.activeStockId, { quiet: true, keepSheet: true });
    }
    window.setTimeout(hideMessage, failed > 0 ? 4200 : 2200);
  } catch (error) {
    showMessage(`更新波段提醒資料失敗：${error.message}`, true);
  } finally {
    state.levelsSyncing = false;
    updateLevelsSyncControls();
  }
}

async function syncLevelTarget(stockId) {
  const target = String(stockId || "").trim();
  if (!target || state.levelsSyncing) return;
  state.levelsSyncing = true;
  updateLevelsSyncControls({ text: `更新 ${target}` });
  updateLevelRowSyncState(target, true);
  showMessage(`開始更新 ${target} 的資料...`);
  try {
    const payload = await syncTargetsBatch([target]);
    const ok = Number(payload.succeeded || 0) > 0;
    if (ok) {
      const skipped = Number(payload.skipped || 0) > 0;
      showMessage(skipped ? `${target} 已是最近收盤資料。` : `${target} 資料已更新。`);
      await loadLocalData();
      if (state.activeStockId === target) {
        await loadStock(target, { quiet: true, keepSheet: true });
      }
      window.setTimeout(hideMessage, 1800);
    } else {
      const firstError = (payload.results || []).find((item) => !item.ok)?.error;
      showMessage(`${target} 更新失敗：${firstError || "資料源暫時沒有回應"}`, true);
    }
  } catch (error) {
    showMessage(`${target} 更新失敗：${error.message}`, true);
  } finally {
    state.levelsSyncing = false;
    updateLevelRowSyncState(target, false);
    updateLevelsSyncControls();
  }
}

async function syncTargetsBatch(targets) {
  return syncTargetsConcurrently(targets, Math.min(LEVEL_SYNC_CONCURRENCY, Math.max(1, targets.length)));
}

async function syncTargetsSequentially(targets) {
  return syncTargetsConcurrently(targets, 1);
}

async function syncTargetsConcurrently(targets, concurrency = LEVEL_SYNC_CONCURRENCY) {
  const safeTargets = uniqueStockIds(targets);
  const results = [];
  let rowsWritten = 0;
  let nextIndex = 0;
  let finished = 0;
  const workerCount = Math.min(Math.max(1, concurrency), safeTargets.length || 1);
  const updateProgress = () => {
    const prefix = workerCount > 1 ? `同時 ${workerCount} 檔` : "單檔";
    updateLevelsSyncControls({ text: `更新中 ${finished}/${safeTargets.length}・${prefix}` });
  };
  updateProgress();

  const runOne = async () => {
    while (nextIndex < safeTargets.length) {
      const stockId = safeTargets[nextIndex];
      nextIndex += 1;
      updateLevelRowSyncState(stockId, true);
      try {
        const payload = await postJson("/api/sync", {
          stock_id: stockId,
          lookback_days: STOCK_SYNC_LOOKBACK_DAYS,
          skip_if_current: true,
        });
        const rows = Number(payload.sync?.rows_written || 0);
        const skipped = Boolean(payload.sync?.skipped);
        rowsWritten += rows;
        results.push({
          stock_id: stockId,
          ok: true,
          skipped,
          rows_written: rows,
          message: payload.sync?.message || "",
        });
      } catch (error) {
        results.push({
          stock_id: stockId,
          ok: false,
          error: error.message,
        });
      } finally {
        finished += 1;
        updateLevelRowSyncState(stockId, false);
        updateProgress();
      }
    }
  };

  await Promise.all(Array.from({ length: workerCount }, () => runOne()));
  const succeeded = results.filter((item) => item.ok).length;
  const skipped = results.filter((item) => item.ok && item.skipped).length;
  return {
    requested: safeTargets.length,
    succeeded,
    skipped,
    failed: safeTargets.length - succeeded,
    rows_written: rowsWritten,
    results,
    concurrency: workerCount,
  };
}

async function syncTargetsViaBatchEndpoint(targets) {
  try {
    return await postJson("/api/sync/batch", {
      stock_ids: targets,
      lookback_days: STOCK_SYNC_LOOKBACK_DAYS,
      skip_if_current: true,
    });
  } catch (error) {
    if (!/not found|HTTP 404/i.test(error.message || "")) throw error;
    return syncTargetsSequentially(targets);
  }
}

function uniqueStockIds(values) {
  const ids = [];
  const seen = new Set();
  (values || []).forEach((value) => {
    const id = String(value || "").trim();
    if (!id || seen.has(id)) return;
    seen.add(id);
    ids.push(id);
  });
  return ids;
}

function updateLevelsSyncControls(options = {}) {
  const count = (state.levelTargets || []).length;
  if (elements.levelsSyncButton) {
    elements.levelsSyncButton.disabled = state.levelsSyncing || count === 0;
    elements.levelsSyncButton.classList.toggle("is-active", state.levelsSyncing);
    elements.levelsSyncButton.innerHTML = `${refreshIconMarkup()} ${state.levelsSyncing ? "更新中" : "更新資料"}`;
  }
  if (elements.levelsSyncStatus) {
    elements.levelsSyncStatus.textContent = options.text || (count ? `本地資料・${count} 檔目標` : "本地資料・接近波撐/波壓");
  }
}

function updateLevelRowSyncState(stockId, syncing) {
  const safeId = attrSelectorValue(String(stockId || ""));
  const row = safeId ? document.querySelector(`[data-level-row="${safeId}"]`) : null;
  const button = safeId ? document.querySelector(`[data-level-sync-stock="${safeId}"]`) : null;
  if (row) row.classList.toggle("is-syncing", Boolean(syncing));
  if (button) {
    button.disabled = Boolean(syncing);
    button.innerHTML = `${refreshIconMarkup()} ${syncing ? "更新中" : "更新"}`;
  }
}

function attrSelectorValue(value) {
  return value.replace(/["\\]/g, "\\$&");
}

function filterAndSortLocalDataItems(items, options = {}) {
  const filterMode = options.filter || "all";
  const sortKey = options.sort || "stock_id";
  const levelRank = { "接近波壓": 0, "接近波撐": 1, "正常": 2, "資料不足": 3, "": 4 };
  const keep = (item) => {
    if (filterMode === "stale") return Number(item.stale_days || 0) > 7;
    if (filterMode === "near_resistance") return item.sr_status === "接近波壓";
    if (filterMode === "near_support") return item.sr_status === "接近波撐";
    return true;
  };
  const value = (item) => {
    const stockId = String(item.stock_id || "");
    if (sortKey === "price_rows_desc") return [-Number(item.price_rows || 0), stockId];
    if (sortKey === "last_date_desc") return [String(item.last_date || "").split("").map((ch) => -ch.charCodeAt(0)), stockId];
    if (sortKey === "last_date_asc") return [String(item.last_date || ""), stockId];
    if (sortKey === "level_status") return [levelRank[item.sr_status || ""] ?? 4, stockId];
    return [stockId];
  };
  return (items || [])
    .filter(keep)
    .slice()
    .sort((a, b) => compareLocalDataSortValue(value(a), value(b)));
}

function compareLocalDataSortValue(a, b) {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i += 1) {
    const av = a[i], bv = b[i];
    if (Array.isArray(av) || Array.isArray(bv)) {
      const nested = compareLocalDataSortValue(av || [], bv || []);
      if (nested) return nested;
      continue;
    }
    if (av < bv) return -1;
    if (av > bv) return 1;
  }
  return 0;
}

function updateLocalDataFilterButtons() {
  elements.localDataFilters?.forEach((button) => {
    button.classList.toggle("is-active", (button.dataset.localFilter || "all") === state.localDataFilter);
  });
  if (elements.localDataSort && elements.localDataSort.value !== state.localDataSort) {
    elements.localDataSort.value = state.localDataSort;
  }
}

function renderLocalDataTable(payload) {
  const tbody = elements.localDataRows;
  if (!tbody) return;
  updateLocalDataFilterButtons();
  const allItems = (payload && payload.items) || [];
  const items = filterAndSortLocalDataItems(allItems, {
    filter: state.localDataFilter,
    sort: state.localDataSort,
  });
  if (elements.localDataSummary) {
    const countText = items.length === allItems.length ? `${allItems.length} 檔` : `${items.length} / ${allItems.length} 檔`;
    const targetText = localDataTargetSummary(payload);
    const dateText = targetText
      ? `檢查日 ${payload.generated_at}，${targetText}`
      : `檢查日 ${payload.generated_at}`;
    elements.localDataSummary.textContent = allItems.length
      ? `本地共有 ${countText} 有日線資料（${dateText}）。過期會以紅字標示。`
      : "本地還沒有任何已下載的日線資料；到雷達中心按『開始下載』，或開個股按『同步』。";
  }
  tbody.innerHTML = items.length ? items.map((it) => {
    const stale = it.stale_days > 7;
    const dateCell = `<span class="${stale ? "ld-stale" : ""}">${escapeHtml(it.last_date)}${stale ? `（過期${it.stale_days}天）` : ""}</span>`;
    const sr = it.sr_status && it.sr_status !== "資料不足" ? escapeHtml(it.sr_status) : "—";
    const dataStatus = localDataCoverageLabel(it);
    return `<tr>
      <td>${escapeHtml(it.stock_id)}</td>
      <td>${escapeHtml(it.name || "")}</td>
      <td>${it.price_rows}</td>
      <td>${dateCell}</td>
      <td>${dataStatus}</td>
      <td>${it.has_institutional ? "✓" : "—"}</td>
      <td>${sr}</td>
      <td><button class="table-action" type="button" data-screener-stock="${escapeHtml(it.stock_id)}">看個股</button></td>
    </tr>`;
  }).join("") : `<tr><td colspan="8">${stateMessageHTML("empty", "目前沒有符合條件的資料", "換一個篩選條件，或先同步更多股票。", { compact: true })}</td></tr>`;
}

function localDataTargetSummary(payload) {
  const target = payload?.data_target || {};
  const targetDate = payload?.data_target_date || target.target_date || "";
  if (!targetDate) return "";
  const label = target.snapshot_stale ? "補正目標" : "最近收盤目標";
  const staleHint = target.snapshot_stale ? "（快照待更新）" : "";
  return `${label} ${targetDate}${staleHint}`;
}

function localDataCoverageLabel(item) {
  const price = dataGapShortLabel(item?.price_gap, "日線");
  const inst = dataGapShortLabel(item?.institutional_gap, "法人");
  const target = item?.data_target || {};
  const parts = [];
  if (target.snapshot_stale) {
    parts.push(`<span class="ld-snapshot">快照待更新</span>`);
  }
  parts.push(price);
  if (inst) parts.push(inst);
  return `<span class="ld-coverage">${parts.join("")}</span>`;
}

function dataGapShortLabel(gap, label) {
  const status = gap?.status || "";
  if (status === "current" || status === "patched") {
    return `<span class="ld-ok">${escapeHtml(label)}已最新</span>`;
  }
  if (status === "gap") {
    const days = Number(gap?.gap_business_days || 0);
    return `<span class="ld-gap">${escapeHtml(label)}缺 ${formatInteger(days)} 日</span>`;
  }
  if (status === "force_refresh_required") {
    return `<span class="ld-stale">${escapeHtml(label)}需重建</span>`;
  }
  if (status === "source_pending") {
    return `<span class="ld-muted">${escapeHtml(label)}待來源</span>`;
  }
  return `<span class="ld-muted">${escapeHtml(label)}未索引</span>`;
}
