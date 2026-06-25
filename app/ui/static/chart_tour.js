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
      why: document.querySelector("#chartTourWhy"),
      caution: document.querySelector("#chartTourCaution"),
      dots: document.querySelector("#chartTourDots"),
      play: document.querySelector("#chartTourPlayBtn"),
      speed: document.querySelector("#chartTourSpeedBtn"),
      disclaimer: document.querySelector("#chartTourDisclaimer"),
      callout: document.querySelector("#chartTourCallout"),
      calloutLeader: document.querySelector("#chartTourCalloutLeader"),
      calloutIcon: document.querySelector("#chartTourCalloutIcon"),
      calloutLabel: document.querySelector("#chartTourCalloutLabel"),
      calloutText: document.querySelector("#chartTourCalloutText"),
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
    hideTourDomCallout();
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
    if (!tourState.active || !beat || !tour) {
      hideTourDomCallout();
      return;
    }
    const narration = beat.narration || {};
    ui.chapter.textContent = `${chapterLabel(beat.chapter)} · ${confidenceLabel(beat.confidence)}`;
    ui.progress.textContent = `${tourState.index + 1} / ${tour.beats.length}`;
    ui.why.textContent = narration.why || "--";
    ui.caution.textContent = narration.caution || "--";
    ui.disclaimer.textContent = tour.disclaimer || "讀圖識讀教學 · 描述現在 · 非預測 · 非投資建議";
    updateTourDomCallout(beat);
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
      personality: "可信度",
      confirm: "確認",
      trend: "趨勢",
      position: "位階",
      levels: "關卡",
      momentum: "動能",
      volume: "量能",
      derivation: "來源",
      progression: "階段",
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
    const anchor = chooseTourAnchor(layout, view, targets);
    ctx.save();
    ctx.fillStyle = "rgba(6, 15, 26, .10)";
    ctx.fillRect(layout.padding.left, layout.price.top, layout.innerWidth, layout.price.height);
    drawTourReliabilityFilter(ctx, layout, beat);
    targets.forEach((target) => drawTourTarget(ctx, layout, view, target));
    drawTourConnectionArrows(ctx, layout, view, beat, targets);
    updateTourDomCallout(beat, anchor, layout, view);
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

  function updateTourDomCallout(beat, anchor = null, layout = null, view = null) {
    const ui = tourElements();
    if (!ui.callout || !tourState.active || !beat || !state.chartLargeMode) {
      hideTourDomCallout();
      return;
    }
    const text = tourCalloutText(beat);
    if (!text) {
      hideTourDomCallout();
      return;
    }
    const canvas = document.querySelector("#priceChart");
    const panel = canvas?.closest(".chart-panel");
    if (!canvas || !panel) {
      hideTourDomCallout();
      return;
    }
    const canvasRect = canvas.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const anchorPoint = domAnchorPoint(anchor, layout, canvasRect, panelRect);
    if (ui.calloutLabel) ui.calloutLabel.textContent = `${chapterLabel(beat.chapter)} · ${confidenceLabel(beat.confidence)}`;
    if (ui.calloutText) ui.calloutText.textContent = text;
    if (ui.calloutIcon) ui.calloutIcon.textContent = glyphSymbol(beat.chapter);
    ui.callout.classList.remove("hidden", "is-low");
    ui.callout.classList.toggle("is-low", beat.confidence === "low");
    ui.callout.setAttribute("aria-hidden", "false");
    ui.callout.style.visibility = "hidden";
    ui.callout.style.left = "0px";
    ui.callout.style.top = "0px";
    const placement = placeDomCallout(anchorPoint, canvasRect, panelRect, ui.callout, layout, view);
    ui.callout.style.left = `${placement.x}px`;
    ui.callout.style.top = `${placement.y}px`;
    ui.callout.style.visibility = "";
    updateDomLeader(ui.callout, ui.calloutLeader, anchorPoint, placement);
  }

  function hideTourDomCallout() {
    const ui = tourElements();
    if (!ui.callout) return;
    ui.callout.classList.add("hidden");
    ui.callout.setAttribute("aria-hidden", "true");
  }

  function domAnchorPoint(anchor, layout, canvasRect, panelRect) {
    const local = anchor && Number.isFinite(anchor.x) && Number.isFinite(anchor.y)
      ? anchor
      : { x: canvasRect.width * 0.72, y: canvasRect.height * 0.42 };
    const layoutWidth = layout?.width || canvasRect.width || 1;
    const layoutHeight = layout?.height || canvasRect.height || 1;
    const scaleX = canvasRect.width / layoutWidth;
    const scaleY = canvasRect.height / layoutHeight;
    return {
      x: canvasRect.left - panelRect.left + local.x * scaleX,
      y: canvasRect.top - panelRect.top + local.y * scaleY,
    };
  }

  function placeDomCallout(anchorPoint, canvasRect, panelRect, callout, layout = null, view = null) {
    const width = Math.max(230, Math.min(320, callout.getBoundingClientRect().width || 286));
    const height = Math.max(76, Math.min(126, callout.getBoundingClientRect().height || 86));
    const canvasLeft = canvasRect.left - panelRect.left;
    const canvasTop = canvasRect.top - panelRect.top;
    const canvasRight = canvasLeft + canvasRect.width;
    const canvasBottom = canvasTop + canvasRect.height;
    const bounds = {
      left: canvasLeft + 12,
      right: canvasRight - 12,
      top: canvasTop + 14,
      bottom: Math.max(canvasTop + 120, canvasBottom - 108),
    };
    const candidates = domCalloutCandidates(anchorPoint, bounds, width, height);
    let best = null;
    candidates.forEach((candidate) => {
      const placed = {
        ...candidate,
        x: tourClamp(candidate.x, bounds.left, Math.max(bounds.left, bounds.right - width)),
        y: tourClamp(candidate.y, bounds.top, Math.max(bounds.top, bounds.bottom - height)),
        width,
        height,
      };
      const score = scoreDomCalloutPlacement(placed, anchorPoint, canvasRect, panelRect, layout, view, candidate.bias || 0);
      if (!best || score < best.score) best = { ...placed, score };
    });
    return best || { x: bounds.left, y: bounds.top, width, height };
  }

  function domCalloutCandidates(anchorPoint, bounds, width, height) {
    const midY = (bounds.top + bounds.bottom - height) / 2;
    const lowY = bounds.bottom - height;
    const midX = (bounds.left + bounds.right - width) / 2;
    return [
      { x: bounds.left + 12, y: bounds.top + 10, bias: 8 },
      { x: bounds.left + 12, y: midY, bias: 20 },
      { x: bounds.left + 12, y: lowY, bias: 38 },
      { x: midX, y: bounds.top + 10, bias: 36 },
      { x: midX, y: lowY, bias: 52 },
      { x: bounds.right - width - 12, y: bounds.top + 10, bias: 72 },
      { x: bounds.right - width - 12, y: midY, bias: 96 },
      { x: bounds.right - width - 12, y: lowY, bias: 110 },
      { x: anchorPoint.x - width - 42, y: anchorPoint.y - height * 0.5, bias: 26 },
      { x: anchorPoint.x + 42, y: anchorPoint.y - height * 0.5, bias: 42 },
      { x: anchorPoint.x - width * 0.5, y: anchorPoint.y - height - 34, bias: 34 },
      { x: anchorPoint.x - width * 0.5, y: anchorPoint.y + 34, bias: 70 },
    ];
  }

  function scoreDomCalloutPlacement(rect, anchorPoint, canvasRect, panelRect, layout, view, bias) {
    const canvasLeft = canvasRect.left - panelRect.left;
    const canvasTop = canvasRect.top - panelRect.top;
    const canvasRight = canvasLeft + canvasRect.width;
    const canvasBottom = canvasTop + canvasRect.height;
    const futureLeft = layout?.futureWidth
      ? canvasLeft + (layout.plotRight / Math.max(1, layout.width)) * canvasRect.width
      : null;
    const hover = state.chartHoverPoint;
    const hoverPoint = hover && Number.isFinite(hover.x) && Number.isFinite(hover.y)
      ? { x: canvasLeft + hover.x, y: canvasTop + hover.y }
      : null;
    return bias + scoreCalloutGeometry(
      rect,
      anchorPoint,
      collectCandleRects(canvasRect, panelRect, layout, view),
      collectSupportLineYs(canvasRect, panelRect, layout),
      hoverPoint,
      {
        left: canvasLeft,
        right: canvasRight,
        top: canvasTop,
        bottom: canvasBottom,
        recentLeft: canvasLeft + canvasRect.width * 0.62,
        futureLeft,
        bottomControlTop: canvasBottom - 92,
      },
    );
  }

  function scoreCalloutGeometry(rect, anchorPoint, candleRects = [], srYs = [], hoverPoint = null, bounds = {}) {
    let score = 0;
    if (rectContains(rect, anchorPoint)) score += 900;
    const center = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
    const anchorDistance = Math.hypot(center.x - anchorPoint.x, center.y - anchorPoint.y);
    if (anchorDistance < 96) score += 160 - anchorDistance;
    if (Number.isFinite(bounds?.recentLeft) && rect.x + rect.width > bounds.recentLeft) score += 160;
    if (Number.isFinite(bounds?.futureLeft) && rect.x + rect.width > bounds.futureLeft - 16) score += 220;
    if (hoverPoint && rectDistanceToPoint(rect, hoverPoint) < 72) score += 180;
    candleRects.forEach((candleRect) => {
      const weight = candleRect?.recent ? 1 : 0;
      if (rectsOverlap(rect, candleRect)) score += weight ? 26 : 7;
      const close = candleRect?.close || candleRect?.closePoint;
      if (close && rectContains(rect, close)) score += weight ? 36 : 10;
    });
    srYs.forEach((y) => {
      if (Number.isFinite(y) && y >= rect.y - 8 && y <= rect.y + rect.height + 8) score += 42;
    });
    if (Number.isFinite(bounds?.bottomControlTop) && rect.y + rect.height > bounds.bottomControlTop) score += 120;
    if (
      Number.isFinite(bounds?.top) &&
      Number.isFinite(bounds?.left) &&
      Number.isFinite(bounds?.right) &&
      (rect.y < bounds.top + 6 || rect.x < bounds.left + 6 || rect.x + rect.width > bounds.right - 6)
    ) {
      score += 80;
    }
    return score;
  }

  function collectCandleRects(canvasRect, panelRect, layout, view) {
    if (!layout || !view || !state._priceYOf || typeof chartXOf !== "function") return [];
    const all = state.chartAll || [];
    const canvasLeft = canvasRect.left - panelRect.left;
    const canvasTop = canvasRect.top - panelRect.top;
    const scaleX = canvasRect.width / Math.max(1, layout.width);
    const scaleY = canvasRect.height / Math.max(1, layout.height);
    const rects = [];
    const step = Math.max(1, Math.ceil((view.end - view.start + 1) / 180));
    for (let index = view.start; index <= view.end; index += step) {
      const row = all[index];
      if (!row) continue;
      const high = Number(row.high);
      const low = Number(row.low);
      const close = Number(row.close);
      if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) continue;
      const x = canvasLeft + chartXOf(index, view, layout) * scaleX;
      const yHigh = canvasTop + state._priceYOf(high) * scaleY;
      const yLow = canvasTop + state._priceYOf(low) * scaleY;
      const yClose = canvasTop + state._priceYOf(close) * scaleY;
      const candleRect = {
        x: x - 5,
        y: Math.min(yHigh, yLow) - 2,
        width: 10,
        height: Math.abs(yLow - yHigh) + 4,
        close: { x, y: yClose },
        recent: index > view.end - 45,
      };
      rects.push(candleRect);
    }
    return rects;
  }

  function collectSupportLineYs(canvasRect, panelRect, layout) {
    if (!layout) return [];
    const canvasTop = canvasRect.top - panelRect.top;
    const scaleY = canvasRect.height / Math.max(1, layout.height);
    return (state.chartSRLines || []).reduce((ys, line) => {
      const y = canvasTop + Number(line.y) * scaleY;
      if (Number.isFinite(y)) ys.push(y);
      return ys;
    }, []);
  }

  function updateDomLeader(callout, leader, anchorPoint, placement) {
    if (!leader) return;
    const fromLeft = anchorPoint.x < placement.x;
    const fromX = fromLeft ? 0 : placement.width;
    const fromY = placement.height * 0.5;
    const dx = anchorPoint.x - (placement.x + fromX);
    const dy = anchorPoint.y - (placement.y + fromY);
    const length = Math.max(24, Math.min(220, Math.hypot(dx, dy)));
    leader.style.left = `${fromX}px`;
    leader.style.top = `${fromY}px`;
    leader.style.width = `${length}px`;
    leader.style.transform = `rotate(${Math.atan2(dy, dx)}rad)`;
    leader.style.transformOrigin = fromLeft ? "0 50%" : "0 50%";
  }

  function glyphSymbol(chapter) {
    return {
      confirm: "✓",
      derivation: "↔",
      progression: "⌄",
      momentum: "◒",
      volume: "▮",
      levels: "━",
      watch: "◇",
      scenario: "◖",
      personality: "◌",
      structure: "◌",
    }[chapter] || "●";
  }

  function chooseTourAnchor(layout, view, targets) {
    for (const target of targets) {
      const anchor = tourAnchorForTarget(layout, view, target);
      if (anchor) return anchor;
    }
    return latestVisibleCandleAnchor(layout, view);
  }

  function tourAnchorForTarget(layout, view, target) {
    if (!target || !target.type) return null;
    if (target.type === "ma") return maAnchor(layout, view, target.key);
    if (target.type === "level" || target.type === "watch_level") return levelAnchor(layout, view, target);
    if (target.type === "region") return regionAnchor(layout, view, target);
    if (target.type === "candles") return candlesAnchor(layout, view, target);
    if (target.type === "subplot") return subplotAnchor(layout, view, target.key);
    if (target.type === "scenario_cone") return scenarioAnchor(layout);
    return null;
  }

  function latestVisibleCandleAnchor(layout, view) {
    const all = state.chartAll || [];
    const index = Math.max(view.start, Math.min(view.end, all.length - 1));
    const row = all[index];
    if (!row || !state._priceYOf) return { x: layout.plotRight - 28, y: layout.price.top + 28 };
    return {
      x: chartXOf(index, view, layout),
      y: tourClamp(state._priceYOf(Number(row.close)), layout.price.top + 8, layout.price.top + layout.price.height - 8),
    };
  }

  function maAnchor(layout, view, key) {
    if (!key || typeof featureSeries !== "function" || !state._priceYOf) return null;
    const values = featureSeries(key);
    if (!Array.isArray(values)) return null;
    for (let index = view.end; index >= view.start; index -= 1) {
      const value = Number(values[index]);
      if (!Number.isFinite(value)) continue;
      return { x: chartXOf(index, view, layout), y: state._priceYOf(value) };
    }
    return null;
  }

  function levelAnchor(layout, view, target) {
    const price = Number(target.price);
    if (!Number.isFinite(price) || !state._priceYOf) return null;
    const y = state._priceYOf(price);
    if (y < layout.price.top - 8 || y > layout.price.top + layout.price.height + 8) return null;
    const index = dateIndex(target.origin_date);
    const x = index >= view.start && index <= view.end ? chartXOf(index, view, layout) : layout.plotRight - 28;
    return { x: tourClamp(x, layout.padding.left + 12, layout.plotRight - 12), y };
  }

  function regionAnchor(layout, view, target) {
    const start = dateIndex(target.from_date);
    const end = dateIndex(target.to_date);
    if (start < 0 || end < 0) return null;
    const a = Math.max(view.start, Math.min(start, end));
    const b = Math.min(view.end, Math.max(start, end));
    if (a > b) return null;
    return {
      x: (chartXOf(a, view, layout) + chartXOf(b, view, layout)) / 2,
      y: layout.price.top + layout.price.height * 0.34,
    };
  }

  function candlesAnchor(layout, view, target) {
    const dates = Array.isArray(target.dates) ? target.dates : [];
    for (let offset = dates.length - 1; offset >= 0; offset -= 1) {
      const index = dateIndex(dates[offset]);
      const row = state.chartAll?.[index];
      if (index < view.start || index > view.end || !row || !state._priceYOf) continue;
      return { x: chartXOf(index, view, layout), y: state._priceYOf(Number(row.high)) - 16 };
    }
    return null;
  }

  function subplotAnchor(layout, view, key) {
    const panel = subplotPanel(layout, key);
    if (!panel) return null;
    const index = Math.max(view.start, Math.min(view.end, (state.chartAll || []).length - 1));
    return { x: chartXOf(index, view, layout), y: panel.top + panel.height * 0.36 };
  }

  function scenarioAnchor(layout) {
    if (!layout.futureWidth) return null;
    return { x: layout.plotRight + layout.futureWidth * 0.48, y: layout.price.top + layout.price.height * 0.42 };
  }

  function subplotPanel(layout, key) {
    if (key === "volume") return layout.vol;
    return (layout.subplots || []).find((item) => item.key === key || (Array.isArray(item.keys) && item.keys.includes(key))) || null;
  }

  function drawTourReliabilityFilter(ctx, layout, beat) {
    if (beat.confidence !== "low") return;
    ctx.save();
    ctx.fillStyle = "rgba(156, 174, 194, .13)";
    ctx.fillRect(layout.padding.left, layout.price.top, layout.innerWidth, layout.price.height);
    ctx.strokeStyle = "rgba(168, 184, 201, .42)";
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 7]);
    for (let y = layout.price.top + 8; y < layout.price.top + layout.price.height; y += 13) {
      ctx.beginPath();
      ctx.moveTo(layout.padding.left, y);
      ctx.lineTo(layout.plotRight, y - 18);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.restore();
  }

  function drawTourConnectionArrows(ctx, layout, view, beat, targets) {
    if (!["derivation", "progression"].includes(beat.chapter)) return;
    const anchors = targets.map((target) => tourAnchorForTarget(layout, view, target)).filter(Boolean);
    if (anchors.length < 2) return;
    ctx.save();
    ctx.strokeStyle = beat.chapter === "progression" ? TOUR_GOLD : TOUR_BLUE;
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = 1.6;
    ctx.setLineDash(beat.chapter === "progression" ? [4, 4] : [7, 4]);
    for (let index = 0; index < anchors.length - 1; index += 1) {
      drawTourArrow(ctx, anchors[index], anchors[index + 1]);
    }
    ctx.setLineDash([]);
    if (beat.chapter === "progression") drawTourConvergenceBand(ctx, layout, view, targets);
    ctx.restore();
  }

  function drawTourConvergenceBand(ctx, layout, view, targets) {
    if (!state._priceYOf) return;
    const values = targets
      .filter((target) => target.type === "ma")
      .map((target) => {
        const values = typeof featureSeries === "function" ? featureSeries(target.key) : null;
        return Array.isArray(values) ? Number(values[view.end]) : NaN;
      })
      .filter(Number.isFinite);
    if (values.length < 2) return;
    const top = state._priceYOf(Math.max(...values));
    const bottom = state._priceYOf(Math.min(...values));
    const x = chartXOf(view.end, view, layout);
    const width = Math.min(96, Math.max(36, layout.innerWidth * 0.12));
    ctx.fillStyle = "rgba(228, 184, 79, .12)";
    ctx.strokeStyle = "rgba(228, 184, 79, .68)";
    ctx.setLineDash([3, 4]);
    roundRect(ctx, x - width, Math.min(top, bottom) - 7, width, Math.abs(bottom - top) + 14, 7);
    ctx.fill();
    ctx.stroke();
  }

  function drawTourArrow(ctx, from, to) {
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    const angle = Math.atan2(to.y - from.y, to.x - from.x);
    const len = 8;
    ctx.beginPath();
    ctx.moveTo(to.x, to.y);
    ctx.lineTo(to.x - Math.cos(angle - Math.PI / 6) * len, to.y - Math.sin(angle - Math.PI / 6) * len);
    ctx.lineTo(to.x - Math.cos(angle + Math.PI / 6) * len, to.y - Math.sin(angle + Math.PI / 6) * len);
    ctx.closePath();
    ctx.fill();
  }

  function tourCalloutText(beat) {
    const headline = String(beat?.narration?.headline || "").trim();
    if (["personality", "confirm", "derivation", "progression"].includes(beat.chapter) && isLayerZeroText(headline)) {
      return headline;
    }
    const labels = {
      intro: "先確認這張圖的股票與資料時間。",
      trend: "先看平均線是分開還是糾結。",
      position: "先看價格在最近區間的高低位置。",
      levels: "這幾條水平線是過去留下的關卡。",
      momentum: "副圖像油表，先看力氣是熱還是冷。",
      volume: "先看量柱有沒有一起變亮。",
      events: "最近有幾根形狀比較特別。",
      chips: "旁邊的大戶資料只當背景。",
      fundamental: "公司背景放旁邊輔助理解。",
      structure: "先把這檔的性格當濾鏡。",
      scenario: "扇形只是在看過去範圍。",
      watch: "上下關卡都只是條件式觀察。",
      outro: "把讀圖筆記和決策分開。",
    };
    return labels[beat.chapter] || (isLayerZeroText(headline) ? headline : "先看圖上標記的這一段。");
  }

  function isLayerZeroText(text) {
    return Boolean(text) && !/[0-9０-９%％]|MA|EMA|MACD|KD|RSI|OBV|量比|法人|三大法人|布林/i.test(text);
  }

  function rectContains(rect, point) {
    return point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height;
  }

  function rectsOverlap(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
  }

  function rectDistanceToPoint(rect, point) {
    const dx = Math.max(rect.x - point.x, 0, point.x - (rect.x + rect.width));
    const dy = Math.max(rect.y - point.y, 0, point.y - (rect.y + rect.height));
    return Math.hypot(dx, dy);
  }

  function tourClamp(value, min, max) {
    if (max < min) return min;
    return Math.max(min, Math.min(max, value));
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

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { scoreCalloutGeometry };
  }

  if (typeof window !== "undefined" && typeof document !== "undefined") {
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
  }
})();
