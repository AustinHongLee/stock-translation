"""歷史頻率回測：只描述過去樣本，不預測未來。

把幾個常見技術事件轉成固定條件，統計事件發生後 5/20 個交易日的歷史報酬分布。
輸出包含樣本相對頻率、分位數與常態近似區間；這些都是樣本描述，不是未來機率。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.analyze.levels import compute_support_resistance


FORWARD_WINDOWS = (5, 20)
MIN_ROWS = 80
MIN_NORMAL_SAMPLE_COUNT = 8
RSI_PERIOD = 14
KD_PERIOD = 9

DISCLAIMER = (
    "本區只統計已發生過的歷史樣本：同類事件出現後，過去 5/20 個交易日的報酬分布。"
    "常態近似只是把樣本粗略套成鐘形分布，市場報酬常有偏態與肥尾；這不是預測，也不是買賣建議。"
)


@dataclass(frozen=True, slots=True)
class EventDefinition:
    key: str
    label: str
    description: str
    min_gap: int
    condition: Callable[[int, dict[str, Any]], bool]


def build_historical_frequency_report(
    prices: Sequence[Any],
    *,
    forward_windows: Sequence[int] = FORWARD_WINDOWS,
) -> dict[str, Any]:
    rows = _valid_price_rows(prices)
    if len(rows) < MIN_ROWS:
        return {
            "available": False,
            "title": "歷史頻率回測",
            "summary": f"日線資料不足，至少需要約 {MIN_ROWS} 筆有效交易日。",
            "events": [],
            "disclaimer": DISCLAIMER,
        }

    ctx = _build_context(rows)
    events = [_build_event_payload(definition, ctx, forward_windows) for definition in EVENT_DEFINITIONS]
    visible_events = [
        event
        for event in events
        if event["completed_sample_count"] > 0 or event["current_match"]
    ]
    completed = sum(1 for event in visible_events if event["completed_sample_count"] > 0)
    summary = (
        f"用 {len(rows)} 筆有效日線檢查 {len(EVENT_DEFINITIONS)} 種事件；"
        f"{completed} 種事件在樣本內有可計算的後續分布。"
        "下方數字只描述本檔歷史，不代表下一次也會重演。"
    )

    return {
        "available": True,
        "title": "歷史頻率回測",
        "as_of": rows[-1]["date"],
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "rows": len(rows),
        "summary": summary,
        "events": visible_events,
        "math_note": "常態近似只在樣本至少 8 次時顯示；它是用樣本平均與標準差估出的鐘形分布面積，分位數更能反映偏態與極端值。",
        "disclaimer": DISCLAIMER,
    }


def summarize_forward_returns(values: Sequence[float]) -> dict[str, Any]:
    sample: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            sample.append(number)
    sample.sort()
    count = len(sample)
    if count == 0:
        return {"count": 0, "available": False}

    mean = sum(sample) / count
    median = _percentile(sample, 50)
    stdev = _sample_stdev(sample, mean)
    positive = sum(1 for value in sample if value > 0)
    negative = sum(1 for value in sample if value < 0)
    flat = count - positive - negative

    summary = {
        "available": True,
        "count": count,
        "positive_count": positive,
        "negative_count": negative,
        "flat_count": flat,
        "positive_ratio_percent": _round(positive / count * 100, 1),
        "average_return_percent": _round(mean),
        "median_return_percent": _round(median),
        "stdev_percent": _round(stdev),
        "min_return_percent": _round(sample[0]),
        "max_return_percent": _round(sample[-1]),
        "p10_return_percent": _round(_percentile(sample, 10)),
        "p25_return_percent": _round(_percentile(sample, 25)),
        "p75_return_percent": _round(_percentile(sample, 75)),
        "p90_return_percent": _round(_percentile(sample, 90)),
        "sample_note": _sample_note(count),
    }
    if count >= MIN_NORMAL_SAMPLE_COUNT:
        normal_area = _normal_area_above_zero(mean, stdev)
        summary.update(
            {
                "normal_positive_area_percent": _round(normal_area, 1),
                "normal_68_range_percent": [_round(mean - stdev), _round(mean + stdev)],
                "normal_95_range_percent": [_round(mean - 1.96 * stdev), _round(mean + 1.96 * stdev)],
            }
        )
    return summary


def _build_event_payload(
    definition: EventDefinition,
    ctx: dict[str, Any],
    forward_windows: Sequence[int],
) -> dict[str, Any]:
    n = len(ctx["rows"])
    trigger_indices = _select_trigger_indices(
        [index for index in range(n) if definition.condition(index, ctx)],
        min_gap=definition.min_gap,
    )
    windows: list[dict[str, Any]] = []
    max_sample_count = 0
    for days in forward_windows:
        returns = [
            _forward_return_percent(ctx["closes"], index, days)
            for index in trigger_indices
            if index + days < n
        ]
        stats = summarize_forward_returns(returns)
        max_sample_count = max(max_sample_count, int(stats.get("count") or 0))
        windows.append({"days": int(days), **stats})

    latest_index = trigger_indices[-1] if trigger_indices else None
    return {
        "key": definition.key,
        "label": definition.label,
        "description": definition.description,
        "trigger_count": len(trigger_indices),
        "completed_sample_count": max_sample_count,
        "latest_trigger_date": ctx["rows"][latest_index]["date"] if latest_index is not None else None,
        "current_match": bool(trigger_indices and trigger_indices[-1] == n - 1),
        "windows": windows,
    }


def _build_context(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    rsi_values = _rsi_series(closes)
    kd_values = _kd_series(rows)
    sma20 = _sma_series(closes, 20)
    avg_volume20 = _sma_series(volumes, 20)
    price_position = _price_position_series(closes, 240)
    sr_status = _support_status_series(rows)
    return {
        "rows": rows,
        "closes": closes,
        "rsi": rsi_values,
        "kd": kd_values,
        "sma20": sma20,
        "avg_volume20": avg_volume20,
        "price_position": price_position,
        "sr_status": sr_status,
    }


def _kd_low_cross(index: int, ctx: dict[str, Any]) -> bool:
    if index <= 0:
        return False
    prev = ctx["kd"][index - 1]
    current = ctx["kd"][index]
    if prev is None or current is None:
        return False
    prev_k, prev_d = prev
    k, d = current
    return prev_k <= prev_d and k > d and k <= 35


def _rsi_low_rebound(index: int, ctx: dict[str, Any]) -> bool:
    if index <= 0:
        return False
    prev = ctx["rsi"][index - 1]
    current = ctx["rsi"][index]
    return (
        prev is not None
        and current is not None
        and prev <= 35
        and current <= 45
        and current >= prev + 2
    )


def _ma20_reclaim(index: int, ctx: dict[str, Any]) -> bool:
    if index <= 0:
        return False
    prev_ma = ctx["sma20"][index - 1]
    ma = ctx["sma20"][index]
    if prev_ma is None or ma is None:
        return False
    closes = ctx["closes"]
    return closes[index - 1] <= prev_ma and closes[index] > ma


def _near_support(index: int, ctx: dict[str, Any]) -> bool:
    return ctx["sr_status"][index] == "接近波撐"


def _volume_up_day(index: int, ctx: dict[str, Any]) -> bool:
    avg_volume = ctx["avg_volume20"][index]
    if avg_volume is None or avg_volume <= 0:
        return False
    row = ctx["rows"][index]
    return row["volume"] >= avg_volume * 1.8 and row["close"] > row["open"]


def _high_heat(index: int, ctx: dict[str, Any]) -> bool:
    rsi_value = ctx["rsi"][index]
    kd_value = ctx["kd"][index]
    position = ctx["price_position"][index]
    if rsi_value is None or kd_value is None or position is None:
        return False
    k, _d = kd_value
    return rsi_value >= 70 and k >= 80 and position >= 80


EVENT_DEFINITIONS: tuple[EventDefinition, ...] = (
    EventDefinition(
        "kd_low_cross",
        "KD 低檔交叉",
        "K 由下穿上 D，且 K 值仍在 35 以下。",
        3,
        _kd_low_cross,
    ),
    EventDefinition(
        "rsi_low_rebound",
        "RSI 低位回升",
        "RSI 在低位向上回升，且仍低於 45。",
        3,
        _rsi_low_rebound,
    ),
    EventDefinition(
        "ma20_reclaim",
        "收回月線",
        "收盤由 20 日均線下方回到均線上方。",
        3,
        _ma20_reclaim,
    ),
    EventDefinition(
        "near_support",
        "接近波撐",
        "收盤離近 60 日波段支撐約 2% 內。",
        5,
        _near_support,
    ),
    EventDefinition(
        "volume_up_day",
        "爆量收紅",
        "成交量高於近 20 日均量 1.8 倍，且收盤高於開盤。",
        5,
        _volume_up_day,
    ),
    EventDefinition(
        "high_heat",
        "高檔過熱",
        "RSI >= 70、K >= 80，且價格位階在近一年上緣。",
        5,
        _high_heat,
    ),
)


def _rsi_series(closes: list[float], period: int = RSI_PERIOD) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _kd_series(rows: list[dict[str, Any]], period: int = KD_PERIOD) -> list[tuple[float, float] | None]:
    out: list[tuple[float, float] | None] = [None] * len(rows)
    if len(rows) < period:
        return out
    k = 50.0
    d = 50.0
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    for i in range(period - 1, len(rows)):
        window_low = min(lows[i - period + 1 : i + 1])
        window_high = max(highs[i - period + 1 : i + 1])
        rsv = 50.0 if window_high == window_low else (closes[i] - window_low) / (window_high - window_low) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        out[i] = (k, d)
    return out


def _sma_series(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    rolling = 0.0
    for index, value in enumerate(values):
        rolling += value
        if index >= period:
            rolling -= values[index - period]
        if index >= period - 1:
            out[index] = rolling / period
    return out


def _price_position_series(closes: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for index in range(len(closes)):
        sample = closes[max(0, index - window + 1) : index + 1]
        if len(sample) < 20:
            continue
        lo = min(sample)
        hi = max(sample)
        out[index] = 50.0 if hi == lo else (closes[index] - lo) / (hi - lo) * 100
    return out


def _support_status_series(rows: list[dict[str, Any]]) -> list[str | None]:
    out: list[str | None] = [None] * len(rows)
    for index in range(len(rows)):
        if index < 20:
            continue
        result = compute_support_resistance(rows[: index + 1])
        out[index] = str(result.get("status") or "")
    return out


def _select_trigger_indices(indices: list[int], *, min_gap: int) -> list[int]:
    selected: list[int] = []
    last = -10_000
    for index in indices:
        if index - last >= min_gap:
            selected.append(index)
            last = index
    return selected


def _forward_return_percent(closes: list[float], index: int, days: int) -> float:
    start = closes[index]
    end = closes[index + days]
    return (end - start) / start * 100


def _valid_price_rows(prices: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in prices or []:
        open_price = _field_float(item, "open")
        high = _field_float(item, "high")
        low = _field_float(item, "low")
        close = _field_float(item, "close")
        volume = _field_float(item, "volume")
        if high is None or low is None or close is None:
            continue
        if high <= 0 or low <= 0 or close <= 0 or high < low or close < low or close > high:
            continue
        if open_price is None:
            open_price = close
        if volume is None:
            volume = 0.0
        if volume == 0 and open_price == high == low == close:
            continue
        rows.append(
            {
                "date": _date_text(_get(item, "date")),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return rows


def _field_float(item: Any, key: str) -> float | None:
    value = _get(item, key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * percentile / 100
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return sorted_values[lower]
    weight = pos - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _sample_stdev(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _normal_area_above_zero(mean: float, stdev: float) -> float:
    if stdev == 0:
        if mean > 0:
            return 100.0
        if mean < 0:
            return 0.0
        return 50.0
    z = (0 - mean) / stdev
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return (1 - cdf) * 100


def _sample_note(count: int) -> str:
    if count < 8:
        return "樣本偏少，只能當線索。"
    if count < 20:
        return "樣本有限，請搭配分位數看。"
    return "樣本量尚可，仍需留意極端值。"


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)
