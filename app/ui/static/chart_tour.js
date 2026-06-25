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
  const TOUR_DIM = "rgba(161, 176, 194, .72)";

  function tourElements() {
    ensureTourCalloutElements();
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
      callout: document.querySelector("#chartTourCallout"),
      calloutLeader: document.querySelector("#chartTourCalloutLeader"),
      calloutIcon: document.querySelector("#chartTourCalloutIcon"),
      calloutLabel: document.querySelector("#chartTourCalloutLabel"),
      calloutText: document.querySelector("#chartTourCalloutText"),
    };
  }

  function ensureTourCalloutElements() {
    if (document.querySelector("#chartTourCallout")) return;
    const canvas = document.querySelector("#priceChart");
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;
    const callout = document.createElement("div");
    callout.id = "chartTourCallout";
    callout.className = "chart-tour-callout hidden";
    callout.setAttribute("aria-hidden", "true");
    callout.innerHTML = `
      <div id="chartTourCalloutLeader" class="chart-tour-callout-leader"></div>
      <div class="chart-tour-callout-meta">
        <span id="chartTourCalloutIcon" aria-hidden="true">●</span>
        <b id="chartTourCalloutLabel">讀圖</b>
      </div>
      <p id="chartTourCalloutText">--</p>
    `;
    parent.insertBefore(callout, canvas.nextSibling);
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
    ui.title.textContent = beat.title || "讀圖導覽";
    ui.headline.textContent = narration.headline || "--";
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
    drawTourAnchoredCallout(ctx, layout, beat, anchor);
    updateTourDomCallout(beat, anchor, layout);
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

  function drawTourAnchoredCallout(ctx, layout, beat, anchor) {
    const text = tourCalloutText(beat);
    if (!text || !anchor) return;
    ctx.save();
    ctx.font = "14px Microsoft JhengHei, Segoe UI, Arial";
    const maxTextWidth = Math.min(310, Math.max(190, layout.innerWidth * 0.36));
    const lines = wrapTourText(ctx, text, maxTextWidth, 3);
    ctx.font = "11px Microsoft JhengHei, Segoe UI, Arial";
    const label = `${chapterLabel(beat.chapter)} · ${confidenceLabel(beat.confidence)}`;
    const labelWidth = ctx.measureText(label).width;
    ctx.font = "14px Microsoft JhengHei, Segoe UI, Arial";
    const lineWidth = Math.max(...lines.map((line) => ctx.measureText(line).width), 120);
    const box = {
      width: Math.min(340, Math.max(220, Math.max(labelWidth + 54, lineWidth + 42))),
      height: 50 + lines.length * 19,
    };
    const placement = chooseTourCalloutPlacement(anchor, box, layout);
    const edge = nearestRectPoint(placement, anchor);

    ctx.strokeStyle = "rgba(143, 201, 255, .82)";
    ctx.lineWidth = 1.4;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(edge.x, edge.y);
    const midX = (edge.x + anchor.x) / 2;
    const midY = (edge.y + anchor.y) / 2;
    ctx.quadraticCurveTo(midX, midY - 10, anchor.x, anchor.y);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "rgba(8, 20, 32, .94)";
    ctx.strokeStyle = beat.confidence === "low" ? TOUR_DIM : TOUR_BLUE;
    ctx.shadowColor = "rgba(0, 0, 0, .30)";
    ctx.shadowBlur = 18;
    roundRect(ctx, placement.x, placement.y, box.width, box.height, 8);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.stroke();

    drawTourVisualGlyph(ctx, beat, placement.x + 18, placement.y + 24, 17);
    ctx.fillStyle = TOUR_DIM;
    ctx.font = "11px Microsoft JhengHei, Segoe UI, Arial";
    ctx.fillText(label, placement.x + 42, placement.y + 21);
    ctx.fillStyle = TOUR_INK;
    ctx.font = "14px Microsoft JhengHei, Segoe UI, Arial";
    lines.forEach((line, index) => {
      ctx.fillText(line, placement.x + 18, placement.y + 47 + index * 19);
    });

    ctx.fillStyle = beat.confidence === "low" ? TOUR_DIM : TOUR_GOLD;
    ctx.beginPath();
    ctx.arc(anchor.x, anchor.y, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function updateTourDomCallout(beat, anchor = null, layout = null) {
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
    const placement = placeDomCallout(anchorPoint, canvasRect, panelRect, ui.callout);
    ui.callout.classList.remove("hidden", "is-low");
    ui.callout.classList.toggle("is-low", beat.confidence === "low");
    ui.callout.setAttribute("aria-hidden", "false");
    ui.callout.style.left = `${placement.x}px`;
    ui.callout.style.top = `${placement.y}px`;
    if (ui.calloutLabel) ui.calloutLabel.textContent = `${chapterLabel(beat.chapter)} · ${confidenceLabel(beat.confidence)}`;
    if (ui.calloutText) ui.calloutText.textContent = text;
    if (ui.calloutIcon) ui.calloutIcon.textContent = glyphSymbol(beat.chapter);
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

  function placeDomCallout(anchorPoint, canvasRect, panelRect, callout) {
    const width = Math.max(230, Math.min(320, callout.getBoundingClientRect().width || 286));
    const height = Math.max(76, Math.min(126, callout.getBoundingClientRect().height || 86));
    const canvasLeft = canvasRect.left - panelRect.left;
    const canvasTop = canvasRect.top - panelRect.top;
    const canvasRight = canvasLeft + canvasRect.width;
    const canvasBottom = canvasTop + canvasRect.height;
    const preferLeft = anchorPoint.x > canvasLeft + canvasRect.width * 0.58;
    const x = preferLeft
      ? canvasLeft + 26
      : Math.min(anchorPoint.x + 34, canvasRight - width - 18);
    const y = tourClamp(anchorPoint.y - height * 0.52, canvasTop + 14, Math.max(canvasTop + 14, canvasBottom - height - 88));
    return {
      x: tourClamp(x, canvasLeft + 12, Math.max(canvasLeft + 12, canvasRight - width - 12)),
      y,
      width,
      height,
    };
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

  function chooseTourCalloutPlacement(anchor, box, layout) {
    const bounds = {
      left: layout.padding.left + 8,
      right: layout.plotRight - 8,
      top: layout.price.top + 8,
      bottom: Math.max(layout.price.top + 120, layout.height - layout.padding.bottom - 82),
    };
    const candidates = [
      { side: "safe-left", x: layout.padding.left + 18, y: anchor.y - box.height / 2 },
      { side: "left", x: anchor.x - box.width - 28, y: anchor.y - box.height / 2 },
      { side: "right", x: anchor.x + 28, y: anchor.y - box.height / 2 },
      { side: "above", x: anchor.x - box.width / 2, y: anchor.y - box.height - 30 },
      { side: "below", x: anchor.x - box.width / 2, y: anchor.y + 30 },
    ];
    const anchorInRecentZone = anchor.x > layout.padding.left + layout.innerWidth * 0.70;
    const recentZoneLeft = layout.padding.left + layout.innerWidth * 0.64;
    let best = null;
    candidates.forEach((candidate) => {
      const raw = { ...candidate, width: box.width, height: box.height };
      const placed = {
        ...raw,
        x: tourClamp(raw.x, bounds.left, bounds.right - box.width),
        y: tourClamp(raw.y, bounds.top, bounds.bottom - box.height),
      };
      const overflow = Math.abs(placed.x - raw.x) + Math.abs(placed.y - raw.y);
      const recentPenalty = placed.x + box.width > recentZoneLeft && placed.y < layout.price.top + layout.price.height ? 80 : 0;
      const anchorPenalty = rectContains(placed, anchor) ? 120 : 0;
      const sidePenalty = candidate.side === "right" && anchor.x > recentZoneLeft ? 45 : 0;
      const safeLeftBonus = candidate.side === "safe-left" && anchorInRecentZone ? -55 : 25;
      const score = overflow + recentPenalty + anchorPenalty + sidePenalty + safeLeftBonus;
      if (!best || score < best.score) best = { ...placed, score };
    });
    return best || { x: bounds.left, y: bounds.top, width: box.width, height: box.height };
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

  function drawTourVisualGlyph(ctx, beat, x, y, size) {
    ctx.save();
    ctx.strokeStyle = beat.confidence === "low" ? TOUR_DIM : TOUR_GOLD;
    ctx.fillStyle = beat.confidence === "low" ? "rgba(161, 176, 194, .20)" : "rgba(228, 184, 79, .18)";
    ctx.lineWidth = 1.7;
    const chapter = beat.chapter;
    if (chapter === "confirm") {
      drawMiniArrow(ctx, x - size * 0.65, y + 4, chapterDirection(beat), size * 0.42);
      drawMiniArrow(ctx, x, y + 4, "flat", size * 0.42);
      drawCheckMark(ctx, x + size * 0.68, y + 1, size * 0.45);
    } else if (chapter === "derivation") {
      drawNodeLinkGlyph(ctx, x, y, size);
    } else if (chapter === "progression") {
      drawFunnelGlyph(ctx, x, y, size);
    } else if (chapter === "personality" || chapter === "structure") {
      drawClarityGlyph(ctx, x, y, size, beat.confidence);
    } else if (chapter === "momentum") {
      drawGaugeGlyph(ctx, x, y, size);
    } else if (chapter === "volume") {
      drawBarsGlyph(ctx, x, y, size);
    } else if (chapter === "levels" || chapter === "watch") {
      drawLevelGlyph(ctx, x, y, size);
    } else if (chapter === "scenario") {
      drawFanGlyph(ctx, x, y, size);
    } else {
      drawMarkerGlyph(ctx, x, y, size);
    }
    ctx.restore();
  }

  function drawMiniArrow(ctx, x, y, direction, size) {
    const dy = direction === "down" ? size : direction === "up" ? -size : 0;
    ctx.beginPath();
    ctx.moveTo(x, y - dy * 0.5);
    ctx.lineTo(x, y + dy);
    ctx.stroke();
    if (direction === "flat") {
      ctx.beginPath();
      ctx.moveTo(x - size * 0.45, y);
      ctx.lineTo(x + size * 0.45, y);
      ctx.stroke();
      return;
    }
    const tipY = y + dy;
    ctx.beginPath();
    ctx.moveTo(x, tipY);
    ctx.lineTo(x - size * 0.35, tipY - Math.sign(dy || -1) * size * 0.35);
    ctx.lineTo(x + size * 0.35, tipY - Math.sign(dy || -1) * size * 0.35);
    ctx.closePath();
    ctx.fill();
  }

  function drawCheckMark(ctx, x, y, size) {
    ctx.beginPath();
    ctx.arc(x, y, size, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(x - size * 0.45, y);
    ctx.lineTo(x - size * 0.12, y + size * 0.34);
    ctx.lineTo(x + size * 0.5, y - size * 0.4);
    ctx.stroke();
  }

  function drawNodeLinkGlyph(ctx, x, y, size) {
    const points = [{ x: x - size * 0.65, y }, { x, y: y - size * 0.45 }, { x: x + size * 0.68, y: y + size * 0.36 }];
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    ctx.lineTo(points[1].x, points[1].y);
    ctx.lineTo(points[2].x, points[2].y);
    ctx.stroke();
    points.forEach((point) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, size * 0.22, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    });
  }

  function drawFunnelGlyph(ctx, x, y, size) {
    ctx.beginPath();
    ctx.moveTo(x - size * 0.72, y - size * 0.46);
    ctx.lineTo(x + size * 0.72, y - size * 0.46);
    ctx.lineTo(x + size * 0.3, y + size * 0.1);
    ctx.lineTo(x + size * 0.08, y + size * 0.62);
    ctx.lineTo(x - size * 0.08, y + size * 0.62);
    ctx.lineTo(x - size * 0.3, y + size * 0.1);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  function drawClarityGlyph(ctx, x, y, size, confidence) {
    if (confidence === "low") ctx.setLineDash([2, 3]);
    roundRect(ctx, x - size * 0.6, y - size * 0.5, size * 1.2, size, 4);
    ctx.fill();
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(x - size * 0.42, y);
    ctx.lineTo(x + size * 0.42, y);
    ctx.stroke();
  }

  function drawGaugeGlyph(ctx, x, y, size) {
    ctx.beginPath();
    ctx.arc(x, y + size * 0.38, size * 0.72, Math.PI, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x, y + size * 0.38);
    ctx.lineTo(x + size * 0.38, y - size * 0.12);
    ctx.stroke();
  }

  function drawBarsGlyph(ctx, x, y, size) {
    [-0.5, 0, 0.5].forEach((offset, index) => {
      const h = size * (0.45 + index * 0.18);
      ctx.fillRect(x + offset * size - size * 0.12, y + size * 0.55 - h, size * 0.22, h);
    });
  }

  function drawLevelGlyph(ctx, x, y, size) {
    ctx.beginPath();
    ctx.moveTo(x - size * 0.72, y);
    ctx.lineTo(x + size * 0.72, y);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - size * 0.45, y + size * 0.42);
    ctx.lineTo(x + size * 0.45, y + size * 0.42);
    ctx.moveTo(x - size * 0.32, y + size * 0.42);
    ctx.lineTo(x - size * 0.32, y);
    ctx.moveTo(x + size * 0.32, y + size * 0.42);
    ctx.lineTo(x + size * 0.32, y);
    ctx.stroke();
  }

  function drawFanGlyph(ctx, x, y, size) {
    ctx.beginPath();
    ctx.moveTo(x - size * 0.55, y + size * 0.45);
    ctx.quadraticCurveTo(x, y - size * 0.62, x + size * 0.65, y - size * 0.2);
    ctx.lineTo(x + size * 0.65, y + size * 0.58);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  function drawMarkerGlyph(ctx, x, y, size) {
    ctx.beginPath();
    ctx.arc(x, y, size * 0.54, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  function chapterDirection(beat) {
    const text = `${beat?.narration?.headline || ""} ${beat?.title || ""}`;
    if (text.includes("下跌")) return "down";
    if (text.includes("上漲")) return "up";
    return "flat";
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

  function wrapTourText(ctx, text, maxWidth, maxLines) {
    const chars = Array.from(String(text || ""));
    const lines = [];
    let current = "";
    chars.forEach((char) => {
      const next = current + char;
      if (current && ctx.measureText(next).width > maxWidth) {
        lines.push(current);
        current = char.trimStart();
      } else {
        current = next;
      }
    });
    if (current) lines.push(current);
    if (lines.length > maxLines) {
      const kept = lines.slice(0, maxLines);
      let last = kept[kept.length - 1] || "";
      while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
      kept[kept.length - 1] = `${last}…`;
      return kept;
    }
    return lines.length ? lines : ["先看圖上標記的這一段。"];
  }

  function nearestRectPoint(rect, point) {
    const x = tourClamp(point.x, rect.x, rect.x + rect.width);
    const y = tourClamp(point.y, rect.y, rect.y + rect.height);
    const distances = [
      { x, y: rect.y, d: Math.abs(point.y - rect.y) },
      { x, y: rect.y + rect.height, d: Math.abs(point.y - (rect.y + rect.height)) },
      { x: rect.x, y, d: Math.abs(point.x - rect.x) },
      { x: rect.x + rect.width, y, d: Math.abs(point.x - (rect.x + rect.width)) },
    ];
    return distances.sort((a, b) => a.d - b.d)[0];
  }

  function rectContains(rect, point) {
    return point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height;
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
