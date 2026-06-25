(() => {
  const tourState = {
    active: false,
    index: 0,
    playing: false,
    timer: null,
    speedIndex: 1,
  };
  const SPEEDS = [4000, 5200, 7000];
  const TOUR_BLUE = "#8fc9ff";
  const TOUR_GOLD = "#e4b84f";
  const TOUR_INK = "rgba(231, 242, 255, .92)";

  function tourElements() {
    return {
      button: document.querySelector("#chartTourBtn"),
      overlay: document.querySelector("#chartTourOverlay"),
      chapter: document.querySelector("#chartTourChapter"),
      progress: document.querySelector("#chartTourProgress"),
      title: document.querySelector("#chartTourTitle"),
      headline: document.querySelector("#chartTourHeadline"),
      why: document.querySelector("#chartTourWhy"),
      caution: document.querySelector("#chartTourCaution"),
      dots: document.querySelector("#chartTourDots"),
      play: document.querySelector("#chartTourPlayBtn"),
      speed: document.querySelector("#chartTourSpeedBtn"),
      disclaimer: document.querySelector("#chartTourDisclaimer"),
    };
  }

  function currentTour() {
    const payload = typeof state !== "undefined" ? state.activePayload : null;
    const tour = payload?.chart_tour;
    return tour && Array.isArray(tour.beats) ? tour : null;
  }

  function currentBeat() {
    const tour = currentTour();
    if (!tour?.beats?.length) return null;
    return tour.beats[Math.max(0, Math.min(tourState.index, tour.beats.length - 1))] || null;
  }

  function syncChartTourUi() {
    const ui = tourElements();
    const tour = currentTour();
    const available = Boolean(tour?.available && tour.beats?.length);
    if (ui.button) {
      ui.button.disabled = !available;
      ui.button.classList.toggle("is-active", tourState.active);
      ui.button.title = available
        ? "播放大型 K 線圖讀圖導覽"
        : "這檔目前沒有足夠資料產生讀圖導覽";
    }
    if (tourState.active && !available) stopChartTour({ silent: true });
    renderChartTourPanel();
  }

  function toggleChartTour() {
    if (tourState.active) {
      stopChartTour();
      return;
    }
    startChartTour();
  }

  function startChartTour() {
    const tour = currentTour();
    if (!tour?.available || !tour.beats?.length) {
      showMessage?.("這檔目前沒有足夠資料產生讀圖導覽。", true);
      return;
    }
    if (!state.chartLargeMode) toggleLargeChart(true);
    tourState.active = true;
    tourState.index = 0;
    tourState.playing = true;
    renderChartTourPanel();
    scheduleNextBeat();
    drawChart();
  }

  function stopChartTour(options = {}) {
    clearTourTimer();
    tourState.active = false;
    tourState.playing = false;
    const ui = tourElements();
    ui.overlay?.classList.add("hidden");
    ui.button?.classList.remove("is-active");
    if (!options.silent) drawChart();
  }

  function scheduleNextBeat() {
    clearTourTimer();
    if (!tourState.active || !tourState.playing) return;
    tourState.timer = window.setTimeout(() => {
      stepChartTour(1, { wrap: true });
    }, SPEEDS[tourState.speedIndex]);
  }

  function clearTourTimer() {
    if (tourState.timer) window.clearTimeout(tourState.timer);
    tourState.timer = null;
  }

  function stepChartTour(delta, options = {}) {
    const tour = currentTour();
    if (!tour?.beats?.length) return;
    const next = tourState.index + delta;
    if (next >= tour.beats.length) {
      tourState.index = options.wrap ? 0 : tour.beats.length - 1;
    } else if (next < 0) {
      tourState.index = options.wrap ? tour.beats.length - 1 : 0;
    } else {
      tourState.index = next;
    }
    renderChartTourPanel();
    scheduleNextBeat();
    drawChart();
  }

  function togglePlay() {
    tourState.playing = !tourState.playing;
    renderChartTourPanel();
    scheduleNextBeat();
  }

  function cycleSpeed() {
    tourState.speedIndex = (tourState.speedIndex + 1) % SPEEDS.length;
    renderChartTourPanel();
    scheduleNextBeat();
  }

  function renderChartTourPanel() {
    const ui = tourElements();
    const tour = currentTour();
    const beat = currentBeat();
    if (!ui.overlay) return;
    ui.overlay.classList.toggle("hidden", !tourState.active || !beat);
    if (!tourState.active || !beat || !tour) return;
    const narration = beat.narration || {};
    ui.chapter.textContent = `${chapterLabel(beat.chapter)} · ${confidenceLabel(beat.confidence)}`;
    ui.progress.textContent = `${tourState.index + 1} / ${tour.beats.length}`;
    ui.title.textContent = beat.title || "讀圖導覽";
    ui.headline.textContent = narration.headline || "--";
    ui.why.textContent = narration.why || "--";
    ui.caution.textContent = narration.caution || "--";
    ui.disclaimer.textContent = tour.disclaimer || "讀圖識讀教學 · 描述現在 · 非預測 · 非投資建議";
    if (ui.play) {
      ui.play.textContent = tourState.playing ? "暫停" : "播放";
      ui.play.classList.toggle("is-active", tourState.playing);
    }
    if (ui.speed) ui.speed.textContent = `${Math.round(SPEEDS[tourState.speedIndex] / 1000)}秒`;
    if (ui.dots) {
      ui.dots.innerHTML = tour.beats
        .map((_, index) => `<span class="chart-tour-dot ${index === tourState.index ? "is-active" : ""}"></span>`)
        .join("");
    }
    ui.button?.classList.toggle("is-active", true);
  }

  function chapterLabel(chapter) {
    return {
      intro: "開場",
      trend: "趨勢",
      position: "位階",
      levels: "關卡",
      momentum: "動能",
      volume: "量能",
      events: "事件",
      chips: "籌碼",
      fundamental: "基本面",
      structure: "結構",
      scenario: "情境",
      watch: "觀察清單",
      outro: "收尾",
    }[chapter] || "讀圖";
  }

  function confidenceLabel(value) {
    return { high: "高信心", medium: "中信心", low: "資料少" }[value] || "中信心";
  }

  function drawChartTourOverlay(ctx, layout, view) {
    const beat = currentBeat();
    if (!tourState.active || !beat || !state.chartLargeMode) return;
    const targets = Array.isArray(beat.targets) ? beat.targets : [];
    ctx.save();
    ctx.fillStyle = "rgba(6, 15, 26, .10)";
    ctx.fillRect(layout.padding.left, layout.price.top, layout.innerWidth, layout.price.height);
    targets.forEach((target) => drawTourTarget(ctx, layout, view, target));
    ctx.restore();
  }

  function drawTourTarget(ctx, layout, view, target) {
    if (!target || !target.type) return;
    if (target.type === "ma") drawTourMa(ctx, layout, view, target.key);
    if (target.type === "level" || target.type === "watch_level") drawTourLevel(ctx, layout, view, target);
    if (target.type === "region") drawTourRegion(ctx, layout, view, target);
    if (target.type === "candles") drawTourCandles(ctx, layout, view, target);
    if (target.type === "subplot") drawTourSubplot(ctx, layout, target.key);
    if (target.type === "scenario_cone") drawTourScenario(ctx, layout);
  }

  function drawTourMa(ctx, layout, view, key) {
    if (!key || typeof featureSeries !== "function" || typeof chartXOf !== "function") return;
    const values = featureSeries(key);
    if (!Array.isArray(values) || !state._priceYOf) return;
    ctx.save();
    ctx.strokeStyle = TOUR_BLUE;
    ctx.lineWidth = 3;
    ctx.shadowColor = "rgba(143, 201, 255, .72)";
    ctx.shadowBlur = 12;
    ctx.beginPath();
    let started = false;
    for (let index = view.start; index <= view.end; index += 1) {
      const value = Number(values[index]);
      if (!Number.isFinite(value)) {
        started = false;
        continue;
      }
      const x = chartXOf(index, view, layout);
      const y = state._priceYOf(value);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawTourLevel(ctx, layout, view, target) {
    const price = Number(target.price);
    if (!Number.isFinite(price) || !state._priceYOf) return;
    const y = state._priceYOf(price);
    if (y < layout.price.top - 8 || y > layout.price.top + layout.price.height + 8) return;
    const isWatch = target.type === "watch_level";
    ctx.save();
    ctx.setLineDash(isWatch ? [8, 5] : [5, 4]);
    ctx.strokeStyle = isWatch ? TOUR_GOLD : TOUR_BLUE;
    ctx.lineWidth = isWatch ? 2.4 : 2;
    ctx.shadowColor = isWatch ? "rgba(228, 184, 79, .72)" : "rgba(143, 201, 255, .65)";
    ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.moveTo(layout.padding.left, y);
    ctx.lineTo(layout.plotRight + Math.max(0, layout.futureWidth - 6), y);
    ctx.stroke();
    ctx.setLineDash([]);
    drawTourLabel(ctx, layout.padding.left + 8, y - 8, `${target.label || "關卡"} ${formatTourNumber(price)}`, isWatch);
    if (target.origin_date) drawOriginDot(ctx, layout, view, target.origin_date, price, isWatch);
    ctx.restore();
  }

  function drawOriginDot(ctx, layout, view, date, price, isWatch) {
    const index = dateIndex(date);
    if (index < view.start || index > view.end || !state._priceYOf) return;
    const x = chartXOf(index, view, layout);
    const y = state._priceYOf(price);
    ctx.fillStyle = isWatch ? TOUR_GOLD : TOUR_BLUE;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(8, 18, 28, .9)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  function drawTourRegion(ctx, layout, view, target) {
    const start = dateIndex(target.from_date);
    const end = dateIndex(target.to_date);
    if (start < 0 || end < 0) return;
    const a = Math.max(view.start, Math.min(start, end));
    const b = Math.min(view.end, Math.max(start, end));
    if (a > b) return;
    const x1 = chartXOf(a, view, layout);
    const x2 = chartXOf(b, view, layout);
    ctx.save();
    ctx.fillStyle = "rgba(143, 201, 255, .10)";
    ctx.strokeStyle = "rgba(143, 201, 255, .62)";
    ctx.lineWidth = 1.5;
    ctx.fillRect(x1, layout.price.top, Math.max(2, x2 - x1), layout.price.height);
    ctx.strokeRect(x1, layout.price.top, Math.max(2, x2 - x1), layout.price.height);
    ctx.restore();
  }

  function drawTourCandles(ctx, layout, view, target) {
    const dates = Array.isArray(target.dates) ? target.dates : [];
    dates.forEach((date) => {
      const index = dateIndex(date);
      const row = state.chartAll?.[index];
      if (index < view.start || index > view.end || !row || !state._priceYOf) return;
      const x = chartXOf(index, view, layout);
      const y = state._priceYOf(Number(row.high)) - 12;
      ctx.save();
      ctx.fillStyle = TOUR_GOLD;
      ctx.strokeStyle = "rgba(8, 18, 28, .9)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - 7, y - 11);
      ctx.lineTo(x + 7, y - 11);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    });
  }

  function drawTourSubplot(ctx, layout, key) {
    let panel = null;
    if (key === "volume") panel = layout.vol;
    if (!panel && Array.isArray(layout.subplots)) {
      panel = layout.subplots.find((item) => item.key === key || (Array.isArray(item.keys) && item.keys.includes(key)));
    }
    if (!panel) return;
    ctx.save();
    ctx.strokeStyle = TOUR_GOLD;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(layout.padding.left, panel.top, layout.innerWidth, panel.height);
    ctx.setLineDash([]);
    drawTourLabel(ctx, layout.padding.left + 8, panel.top + 17, subplotLabel(key), true);
    ctx.restore();
  }

  function drawTourScenario(ctx, layout) {
    const left = layout.plotRight + 6;
    const width = Math.max(72, layout.futureWidth - 12);
    if (!layout.futureWidth) return;
    ctx.save();
    ctx.strokeStyle = TOUR_GOLD;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(left, layout.price.top, width, layout.price.height);
    ctx.setLineDash([]);
    drawTourLabel(ctx, left + 8, layout.price.top + 20, "歷史情境扇形", true);
    ctx.restore();
  }

  function drawTourLabel(ctx, x, y, text, gold = false) {
    const safe = String(text || "");
    ctx.save();
    ctx.font = "12px Microsoft JhengHei, Segoe UI, Arial";
    const width = Math.min(260, ctx.measureText(safe).width + 16);
    const px = Math.max(8, Math.min(x, (ctx.canvas.width / (window.devicePixelRatio || 1)) - width - 8));
    const py = Math.max(20, y);
    ctx.fillStyle = gold ? "rgba(45, 35, 10, .92)" : "rgba(13, 35, 55, .92)";
    ctx.strokeStyle = gold ? TOUR_GOLD : TOUR_BLUE;
    ctx.lineWidth = 1;
    roundRect(ctx, px, py - 17, width, 24, 6);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = TOUR_INK;
    ctx.fillText(safe, px + 8, py);
    ctx.restore();
  }

  function roundRect(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + width - r, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + r);
    ctx.lineTo(x + width, y + height - r);
    ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
    ctx.lineTo(x + r, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
  }

  function dateIndex(date) {
    if (!date || !Array.isArray(state.chartAll)) return -1;
    return state.chartAll.findIndex((item) => String(item?.date || "") === String(date));
  }

  function subplotLabel(key) {
    return { kd: "KD 副圖", rsi: "RSI 副圖", macd: "MACD 副圖", volume: "成交量" }[key] || "副圖";
  }

  function formatTourNumber(value) {
    if (typeof formatNumber === "function") return formatNumber(value);
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) : "--";
  }

  document.querySelector("#chartTourOverlay")?.addEventListener("click", (event) => {
    const action = event.target.closest("[data-chart-tour-action]")?.dataset.chartTourAction;
    if (!action) return;
    if (action === "prev") stepChartTour(-1);
    if (action === "next") stepChartTour(1);
    if (action === "play") togglePlay();
    if (action === "speed") cycleSpeed();
    if (action === "close") stopChartTour();
  });

  document.addEventListener("keydown", (event) => {
    if (!tourState.active) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      stopChartTour();
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      stepChartTour(1);
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepChartTour(-1);
    }
    if (event.key === " ") {
      event.preventDefault();
      togglePlay();
    }
  }, true);

  window.toggleChartTour = toggleChartTour;
  window.stopChartTour = stopChartTour;
  window.syncChartTourUi = syncChartTourUi;
  window.drawChartTourOverlay = drawChartTourOverlay;
  syncChartTourUi();
})();
