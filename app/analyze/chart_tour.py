"""Guided chart-reading tour assembled from an existing stock payload.

The tour is a narration layer for the large K chart.  It does not fetch data or
create a new signal engine; it only selects from the payload that the stock page
already built and turns those facts into ordered, guardrail-friendly beats.
"""
from __future__ import annotations

import math
from typing import Any


DISCLAIMER = "讀圖識讀教學：描述現在、整理歷史資料，非預測、非投資建議。"
MAX_BEATS = 14

CHAPTER_ORDER = (
    "intro",
    "trend",
    "position",
    "levels",
    "momentum",
    "volume",
    "events",
    "chips",
    "fundamental",
    "structure",
    "scenario",
    "watch",
    "outro",
)
CORE_CHAPTERS = {"intro", "trend", "levels", "events", "watch", "outro"}


def build_chart_tour(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Build the large-chart reading tour from an already assembled payload."""
    data = payload if isinstance(payload, dict) else {}
    prices = _valid_prices(data.get("prices"))
    beats: list[dict[str, Any]] = []
    builders = (
        _intro_beat,
        _trend_beat,
        _position_beat,
        _levels_beat,
        _momentum_beat,
        _volume_beat,
        _events_beat,
        _chips_beat,
        _fundamental_beat,
        _structure_beat,
        _scenario_beat,
        _watch_beat,
        _outro_beat,
    )
    for builder in builders:
        beat = builder(data, prices)
        if beat:
            beats.append(beat)

    beats = _cap_beats(beats)
    return {
        "available": bool(beats),
        "version": 1,
        "title": "讀圖導覽",
        "disclaimer": DISCLAIMER,
        "beats": beats,
    }


def _beat(
    beat_id: str,
    chapter: str,
    title: str,
    *,
    headline: str,
    why: str,
    caution: str,
    source: str,
    targets: list[dict[str, Any]] | None = None,
    confidence: str = "medium",
    priority: int = 50,
) -> dict[str, Any]:
    return {
        "id": beat_id,
        "chapter": chapter,
        "title": title,
        "targets": targets or [],
        "narration": {
            "headline": headline,
            "why": why,
            "caution": caution or "這段只描述目前資料，請和其他章節交叉閱讀。",
        },
        "source": source,
        "confidence": confidence if confidence in {"high", "medium", "low"} else "medium",
        "priority": priority,
    }


def _intro_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    profile = _dict(payload.get("profile"))
    summary = _dict(payload.get("summary"))
    assessment = _dict(payload.get("assessment"))
    stock = _join(" ", [profile.get("stock_id"), profile.get("short_name") or profile.get("name")]) or "這檔股票"
    latest = _number(summary.get("latest_close"))
    date = summary.get("end_date") or (prices[-1].get("date") if prices else None)
    headline = f"先把 {stock} 當成一張圖來讀：資料日 {date or '未標示'}，最新收盤 {_fmt(latest)}。"
    if assessment.get("available") and assessment.get("counts"):
        counts = _dict(assessment.get("counts"))
        headline += f" 目前整理到偏多解讀 {counts.get('bull', 0)}、偏空解讀 {counts.get('bear', 0)}、中性 {counts.get('neutral', 0)}。"
    return _beat(
        "intro.open",
        "intro",
        "先看這張圖是誰",
        headline=headline,
        why="技術派讀圖前會先確認股票、資料日期與最新收盤，避免把不同時間的資料混在一起。",
        caution="這只是讀圖開場，不代表方向判斷，也不取代資料同步檢查。",
        source="profile/summary/assessment",
        targets=[],
        confidence=_confidence_from_rows(summary.get("rows")),
        priority=100,
    )


def _trend_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest = _latest_features(payload)
    ma5 = _number(latest.get("ma5"))
    ma20 = _number(latest.get("ma20"))
    ma60 = _number(latest.get("ma60"))
    if ma5 is None and ma20 is None and ma60 is None:
        return None
    targets = [{"type": "ma", "key": key} for key, value in (("ma5", ma5), ("ma20", ma20), ("ma60", ma60)) if value is not None]
    if ma5 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma20 > ma60:
            shape = "短中長均線由上到下排列，圖上先看短線平均是否仍貼在中期平均上方。"
        elif ma5 < ma20 < ma60:
            shape = "短中長均線由下到上排列，圖上先看價格是否仍壓在中期平均附近。"
        else:
            shape = "短中長均線交錯，圖上比較像整理或方向尚未集中。"
    else:
        shape = "均線資料不完整，先看有資料的均線位置。"
    slope20 = _number(latest.get("ma20_slope"))
    if slope20 is not None:
        shape += f" MA20 近幾根變化約 {_fmt_pct(slope20)}。"
    return _beat(
        "trend.ma_alignment",
        "trend",
        "先描均線骨架",
        headline=shape,
        why="均線把每天收盤平滑成短、中、長三條參考線，常用來看圖形是否集中在同一方向或互相糾結。",
        caution="均線是落後整理，遇到盤整或急轉時會慢半拍，不能單獨當作操作指令。",
        source="features.latest.ma*",
        targets=targets,
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=60),
        priority=95,
    )


def _position_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    summary = _dict(payload.get("summary"))
    latest = _latest_features(payload)
    position = _number(summary.get("price_position"))
    dist_high = _number(latest.get("distance_to_52w_high"))
    dist_low = _number(latest.get("distance_to_52w_low"))
    if position is None and dist_high is None and dist_low is None:
        return None
    parts = []
    if position is not None:
        parts.append(f"目前大約在近一年區間的 {round(position * 100)}% 位置")
    if dist_high is not None:
        parts.append(f"距 52 週高點 {_fmt_pct(dist_high)}")
    if dist_low is not None:
        parts.append(f"距 52 週低點 {_fmt_pct(dist_low)}")
    from_date = prices[0].get("date") if prices else None
    to_date = prices[-1].get("date") if prices else None
    return _beat(
        "position.range",
        "position",
        "再看所在位階",
        headline="；".join(parts) + "。",
        why="位階讓人知道價格現在是在一年範圍的上緣、中段或下緣，避免只盯最後一根 K 棒。",
        caution="相對高低只描述位置，強勢可能停在高位，弱勢也可能停在低位，仍要搭配趨勢與量能。",
        source="summary.price_position/features.latest.distance_to_52w_*",
        targets=[{"type": "region", "from_date": from_date, "to_date": to_date}],
        confidence=_confidence_from_rows(len(prices), required=120),
        priority=70,
    )


def _levels_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    levels = _level_candidates(payload, prices)
    if not levels:
        return None
    close = _last_close(prices)
    chosen = _nearest_levels(levels, close, limit=2)
    if not chosen:
        return None
    labels = "、".join(f"{item['label']} {_fmt(item['price'])}" for item in chosen)
    return _beat(
        "levels.rolling",
        "levels",
        "找過去留下的關卡",
        headline=f"圖上先標出 {labels}，它們來自近期高低點整理。",
        why="支撐與壓力是把過去反覆被碰到或轉折的位置畫成參考線，用來觀察價格靠近哪一側。",
        caution="關卡只來自歷史位置，沒有突破或跌破前，都只是區間參考。",
        source="features.latest.high_low_rolling",
        targets=[_level_target(item) for item in chosen],
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=60),
        priority=90,
    )


def _momentum_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest = _latest_features(payload)
    rsi = _number(latest.get("rsi_14") or latest.get("rsi_12"))
    kd_k = _number(latest.get("kd_k"))
    kd_d = _number(latest.get("kd_d"))
    macd = _number(latest.get("macd"))
    snippets = []
    targets: list[dict[str, Any]] = []
    if kd_k is not None and kd_d is not None:
        snippets.append(f"KD 目前 K {_fmt(kd_k)} / D {_fmt(kd_d)}")
        targets.append({"type": "subplot", "key": "kd"})
    if rsi is not None:
        snippets.append(f"RSI 約 {_fmt(rsi)}")
        targets.append({"type": "subplot", "key": "rsi"})
    if macd is not None:
        snippets.append(f"MACD DIF 約 {_fmt(macd)}")
        targets.append({"type": "subplot", "key": "macd"})
    if not snippets:
        return None
    return _beat(
        "momentum.oscillators",
        "momentum",
        "看動能有沒有過熱或降溫",
        headline="；".join(snippets) + "。",
        why="KD、RSI、MACD 會把近期漲跌速度整理成副圖，幫忙看動能位置和轉折是否需要更多確認。",
        caution="震盪指標在強趨勢中可能停留很久，不能只看高低檔就下結論。",
        source="features.latest.kd/rsi/macd",
        targets=targets,
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=35),
        priority=65,
    )


def _volume_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest = _latest_features(payload)
    ratio = _number(latest.get("volume_ratio"))
    obv_trend = _number(latest.get("volume_trend"))
    if ratio is None and obv_trend is None:
        return None
    headline = []
    if ratio is not None:
        headline.append(f"最新量比約 {_fmt(ratio)} 倍")
    if obv_trend is not None:
        headline.append(f"OBV 近幾根斜率約 {_fmt_pct(obv_trend)}")
    return _beat(
        "volume.confirmation",
        "volume",
        "用量能確認參與度",
        headline="；".join(headline) + "。",
        why="成交量代表市場參與度，技術派常把價格變化和量能一起看，避免只看價格線。",
        caution="量大只表示交易熱度變高，不自動代表方向；量縮也可能只是等待新資料。",
        source="features.latest.volume_ratio/obv",
        targets=[{"type": "subplot", "key": "volume"}],
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=20),
        priority=60,
    )


def _events_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    events = _recent_feature_events(payload, limit=3)
    if not events:
        return None
    labels = "、".join(event["label"] for event in events)
    return _beat(
        "events.recent_candles",
        "events",
        "標出最近的特殊 K 棒",
        headline=f"最近圖上可標出：{labels}。",
        why="缺口、突破或長實體這類 K 棒，是技術派常拿來回看市場反應的位置。",
        caution="單一事件只代表那一天的形狀，後續仍要看是否被回補、延續或重新整理。",
        source="features.series.gap/breakout/candle",
        targets=[{"type": "candles", "dates": [event["date"] for event in events], "label": "近期事件"}],
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=30),
        priority=85,
    )


def _chips_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    chips = _dict(payload.get("chips"))
    if not chips.get("available"):
        return None
    latest = _dict(chips.get("latest"))
    total = _number(latest.get("total_net"))
    sum20 = _number(_dict(chips.get("sum_20")).get("total_net"))
    days = _dict(chips.get("sum_20")).get("days")
    headline = f"三大法人最新合計 {_fmt_lots(total)}，近 {days or 20} 日合計 {_fmt_lots(sum20)}。"
    return _beat(
        "chips.institutional",
        "chips",
        "旁看法人籌碼",
        headline=headline,
        why="法人買賣超可當成籌碼背景，幫助讀圖時知道近期大戶資料是偏流入、流出或混合。",
        caution="法人資料可能落後且有避險、調節等原因，只能當背景，不能單獨解讀。",
        source="chips.latest/sum_20",
        targets=[],
        confidence=_confidence_from_rows(chips.get("days"), required=20),
        priority=45,
    )


def _fundamental_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    revenue = _dict(payload.get("revenue_summary"))
    financial = _dict(payload.get("financial_summary"))
    if not revenue.get("available") and not financial.get("available"):
        return None
    snippets = []
    if revenue.get("available"):
        yoy = _fact_value(revenue, "年增率")
        snippets.append(f"月營收年增 {_fmt_pct(yoy)}" if _number(yoy) is not None else str(revenue.get("title") or "營收資料已同步"))
    if financial.get("available"):
        eps = _fact_value(financial, "EPS")
        snippets.append(f"EPS {_fmt(eps)}" if _number(eps) is not None else str(financial.get("title") or "財報資料已同步"))
    return _beat(
        "fundamental.context",
        "fundamental",
        "補一眼基本面背景",
        headline="；".join(snippets) + "。",
        why="技術派仍會看公司背景，因為營收與獲利能幫忙理解圖形背後是不是有資料變化。",
        caution="基本面更新頻率低於股價，這裡只當背景，不把財報數字轉成價格判斷。",
        source="revenue_summary/financial_summary",
        targets=[],
        confidence="medium",
        priority=40,
    )


def _structure_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    structure = _dict(payload.get("structure"))
    dimensions = [item for item in structure.get("dimensions") or [] if isinstance(item, dict) and not item.get("locked")]
    if not structure.get("available") or not dimensions:
        return None
    top = sorted(dimensions, key=lambda item: int(item.get("level") or 0), reverse=True)[:3]
    labels = "、".join(str(item.get("label") or item.get("key")) for item in top)
    suff = _dict(structure.get("sufficiency")).get("label") or _dict(structure.get("sufficiency")).get("grade")
    return _beat(
        "structure.fingerprint",
        "structure",
        "看這檔股票的結構性格",
        headline=f"結構指紋較突出的面向是：{labels}。資料充足度：{suff or '未標示'}。",
        why="結構指紋把最近一段價格路徑整理成延續性、複雜度、波動聚集等性格描述。",
        caution="這是歷史路徑的性格整理，不是情境推演，也不表示接下來必然延續。",
        source="structure.dimensions",
        targets=[],
        confidence=_confidence_from_structure(structure),
        priority=35,
    )


def _scenario_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    report = _dict(payload.get("historical_frequency"))
    events = [item for item in report.get("events") or [] if isinstance(item, dict)]
    if not report.get("available") or not events:
        return None
    current = next((item for item in events if item.get("current_match")), None)
    event = current or max(events, key=lambda item: int(item.get("completed_sample_count") or 0))
    label = event.get("label") or "相似事件"
    count = event.get("completed_sample_count") or 0
    return _beat(
        "scenario.history",
        "scenario",
        "對照過去相似情境",
        headline=f"歷史情境目前可參考「{label}」，已完成樣本數 {count}。",
        why="情境扇形只把過去類似事件之後的分布畫出來，幫助理解歷史範圍曾經多寬。",
        caution="這不是未來路徑，也不是樣本外推；樣本少時只能當背景。",
        source="historical_frequency.events",
        targets=[{"type": "scenario_cone"}],
        confidence="high" if int(count or 0) >= 8 else "low",
        priority=30,
    )


def _watch_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    close = _last_close(prices)
    levels = _level_candidates(payload, prices)
    if close is None or not levels:
        return None
    above = sorted([item for item in levels if _number(item.get("price")) and float(item["price"]) > close], key=lambda item: float(item["price"]))
    below = sorted([item for item in levels if _number(item.get("price")) and float(item["price"]) < close], key=lambda item: float(item["price"]), reverse=True)
    targets: list[dict[str, Any]] = []
    lines = []
    if above:
        first = above[0]
        nxt = above[1] if len(above) > 1 else None
        targets.append({
            "type": "watch_level",
            "price": first["price"],
            "label": "上方觀察關卡",
            "condition": "break_above",
            "next_price": nxt.get("price") if nxt else first["price"],
        })
        lines.append(f"如果突破 {_fmt(first['price'])} 且後續仍站在其上，技術派接著觀察上方 {_fmt(nxt.get('price') if nxt else first['price'])}。")
    if below:
        first = below[0]
        nxt = below[1] if len(below) > 1 else None
        targets.append({
            "type": "watch_level",
            "price": first["price"],
            "label": "下方觀察關卡",
            "condition": "break_below",
            "next_price": nxt.get("price") if nxt else first["price"],
        })
        lines.append(f"如果跌破 {_fmt(first['price'])}，技術派接著觀察下方 {_fmt(nxt.get('price') if nxt else first['price'])}。")
    if not targets:
        return None
    lines.append("沒突破/跌破前，都只是區間；突破才算數。")
    return _beat(
        "watch.conditional_levels",
        "watch",
        "最後列出接下來盯的關卡",
        headline=" ".join(lines),
        why="讀圖收尾會把上方與下方的條件式關卡列出來，讓後續觀察有清楚檢查點。",
        caution="這是條件式觀察清單，不是路徑預測，也不是價格承諾。",
        source="features.latest.rolling_levels",
        targets=targets,
        confidence=_confidence_from_rows(_feature_visible_rows(payload), required=60),
        priority=92,
    )


def _outro_beat(payload: dict[str, Any], prices: list[dict[str, Any]]) -> dict[str, Any] | None:
    summary = _dict(payload.get("summary"))
    end_date = summary.get("end_date") or (prices[-1].get("date") if prices else None)
    rows = summary.get("rows") or len(prices)
    return _beat(
        "outro.guardrail",
        "outro",
        "收尾：把讀圖和決策分開",
        headline=f"這段導覽用 {rows or 0} 筆日線整理到 {end_date or '未標示'}；請把它當讀圖筆記。",
        why="好的讀圖流程會留下觀察順序與關卡，而不是把單一指標變成答案。",
        caution=DISCLAIMER,
        source="fixed_guardrail/summary",
        targets=[],
        confidence=_confidence_from_rows(rows),
        priority=99,
    )


def _valid_prices(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        close = _number(item.get("close"))
        high = _number(item.get("high"))
        low = _number(item.get("low"))
        if close is None or high is None or low is None or high < low:
            continue
        rows.append({**item, "close": close, "high": high, "low": low})
    return rows


def _latest_features(payload: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(payload.get("features")).get("latest"))


def _feature_visible_rows(payload: dict[str, Any]) -> int:
    warmup = _dict(_dict(payload.get("features")).get("warmup"))
    return int(_number(warmup.get("visible_rows")) or len(_dict(payload.get("features")).get("dates") or []))


def _level_candidates(payload: dict[str, Any], prices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = _latest_features(payload)
    out: list[dict[str, Any]] = []
    for period, label in ((20, "短線"), (60, "波段"), (120, "長線"), (250, "近年")):
        high = _number(latest.get(f"high_{period}"))
        low = _number(latest.get(f"low_{period}"))
        if high is not None:
            out.append({"price": high, "label": f"{label}壓力", "role": "resistance", "origin_date": _origin_date(prices, "high", high)})
        if low is not None:
            out.append({"price": low, "label": f"{label}支撐", "role": "support", "origin_date": _origin_date(prices, "low", low)})
    return _dedupe_levels(out)


def _nearest_levels(levels: list[dict[str, Any]], close: float | None, *, limit: int) -> list[dict[str, Any]]:
    if close is None:
        return levels[:limit]
    return sorted(levels, key=lambda item: abs(float(item["price"]) - close))[:limit]


def _level_target(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "level",
        "price": item.get("price"),
        "label": item.get("label"),
        "role": item.get("role"),
        "origin_date": item.get("origin_date"),
    }


def _dedupe_levels(levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, float]] = set()
    out: list[dict[str, Any]] = []
    for item in levels:
        price = _number(item.get("price"))
        role = str(item.get("role") or "")
        if price is None:
            continue
        key = (role, round(price, 2))
        if key in seen:
            continue
        seen.add(key)
        item["price"] = round(price, 2)
        out.append(item)
    return out


def _origin_date(prices: list[dict[str, Any]], key: str, value: float) -> str | None:
    best: tuple[float, str | None] | None = None
    for row in prices:
        row_value = _number(row.get(key))
        if row_value is None:
            continue
        diff = abs(row_value - value)
        if best is None or diff <= best[0]:
            best = (diff, str(row.get("date")) if row.get("date") else None)
    return best[1] if best else None


def _recent_feature_events(payload: dict[str, Any], *, limit: int) -> list[dict[str, str]]:
    features = _dict(payload.get("features"))
    dates = [str(item) for item in features.get("dates") or []]
    series = _dict(features.get("series"))
    candidates = (
        ("gap_up", "向上缺口"),
        ("gap_down", "向下缺口"),
        ("breakout_20", "突破20日前高"),
        ("breakdown_20", "跌破20日前低"),
        ("long_body", "長實體K"),
        ("doji", "十字線"),
    )
    events: list[dict[str, str]] = []
    for index in range(len(dates) - 1, max(-1, len(dates) - 31), -1):
        labels = [label for key, label in candidates if _series_value(series, key, index) is True]
        if labels:
            events.append({"date": dates[index], "label": f"{dates[index]} {labels[0]}"})
        if len(events) >= limit:
            break
    return list(reversed(events))


def _series_value(series: dict[str, Any], key: str, index: int) -> Any:
    values = series.get(key)
    if not isinstance(values, list) or index < 0 or index >= len(values):
        return None
    return values[index]


def _fact_value(payload: dict[str, Any], label: str) -> Any:
    for fact in payload.get("facts") or []:
        if isinstance(fact, dict) and fact.get("label") == label:
            return fact.get("value")
    return None


def _cap_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(beats, key=lambda item: CHAPTER_ORDER.index(item["chapter"]) if item["chapter"] in CHAPTER_ORDER else 999)
    if len(ordered) <= MAX_BEATS:
        return [_strip_priority(item) for item in ordered]
    core = [item for item in ordered if item["chapter"] in CORE_CHAPTERS]
    optional = sorted((item for item in ordered if item["chapter"] not in CORE_CHAPTERS), key=lambda item: int(item.get("priority") or 0), reverse=True)
    keep_ids = {id(item) for item in (core + optional[: max(0, MAX_BEATS - len(core))])}
    return [_strip_priority(item) for item in ordered if id(item) in keep_ids][:MAX_BEATS]


def _strip_priority(beat: dict[str, Any]) -> dict[str, Any]:
    out = dict(beat)
    out.pop("priority", None)
    return out


def _last_close(prices: list[dict[str, Any]]) -> float | None:
    return _number(prices[-1].get("close")) if prices else None


def _confidence_from_rows(rows: Any, *, required: int = 120) -> str:
    count = int(_number(rows) or 0)
    if count >= required:
        return "high"
    if count >= max(20, required // 2):
        return "medium"
    return "low"


def _confidence_from_structure(structure: dict[str, Any]) -> str:
    grade = str(_dict(structure.get("sufficiency")).get("grade") or "")
    if grade in {"high", "good"}:
        return "high"
    if grade in {"medium", "partial"}:
        return "medium"
    return "low"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fmt(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _fmt_pct(value: Any) -> str:
    number = _number(value)
    return "--" if number is None else f"{number:+.1f}%"


def _fmt_lots(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.0f} 股"


def _join(separator: str, values: list[Any]) -> str:
    return separator.join(str(value) for value in values if value not in (None, ""))
