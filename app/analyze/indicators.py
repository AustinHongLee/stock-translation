"""OHLCV feature engine for the large chart.

Input rows must be chronological. The engine computes features once over the
full warmup window, then optionally slices the returned series to visible dates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from app.analyze.indicator_registry import FEATURE_SPECS, indicator_catalog
from app.analyze.patterns import detect_patterns
from app.analyze.scores import compute_scores

SMA_PERIODS = (5, 10, 20, 60, 120, 240)
EMA_PERIODS = (5, 12, 26, 50, 200)
RETURN_PERIODS = (1, 3, 5, 10, 20, 60, 120, 250)
MOMENTUM_PERIODS = (5, 10, 20)
ATR_PERIODS = (5, 14, 20)
HV_PERIODS = (20, 60, 120)
VOLUME_MA_PERIODS = (5, 20, 60)
ROLLING_SR_PERIODS = (20, 60, 120, 250)
BREAKOUT_PERIODS = (20, 60, 120)
RSI_PERIODS = (6, 12, 14, 24)
SLOPE_LAG = 5
EXPERIMENTAL_DISCLAIMER = "型態與分數只描述目前歷史資料形狀，非投資建議、不預測股價。"


JsonValue = Any


@dataclass(slots=True)
class FeatureBundle:
    dates: list[str]
    series: dict[str, list[JsonValue]]
    latest: dict[str, JsonValue]
    warmup: dict[str, object]

    def to_json(self, *, include_catalog: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "available": bool(self.dates),
            "dates": self.dates,
            "series": self.series,
            "latest": self.latest,
            "warmup": self.warmup,
        }
        if include_catalog:
            payload["catalog"] = indicator_catalog()
        return payload


def compute_features(
    prices: Sequence[Any],
    *,
    visible_dates: Sequence[str] | None = None,
) -> FeatureBundle:
    rows = _valid_price_rows(prices)
    if not rows:
        return _empty_bundle(input_rows=len(prices or []))

    dates = [row["date"] for row in rows]
    closes = [row["close"] for row in rows]
    series = _compute_full_series(rows)

    if visible_dates is None:
        indices = list(range(len(rows)))
    else:
        by_date = {row_date: index for index, row_date in enumerate(dates)}
        indices = [by_date[item] for item in visible_dates if item in by_date]

    sliced_dates = [dates[index] for index in indices]
    sliced = {
        key: [values[index] for index in indices]
        for key, values in series.items()
    }
    latest = {
        key: (values[-1] if values else None)
        for key, values in sliced.items()
    }
    warmup = {
        "input_rows": len(rows),
        "visible_rows": len(indices),
        "warmup_rows": max(0, len(rows) - len(indices)),
        "input_start_date": dates[0],
        "input_end_date": dates[-1],
        "visible_start_date": sliced_dates[0] if sliced_dates else None,
        "visible_end_date": sliced_dates[-1] if sliced_dates else None,
        "longest_required_bars": max(spec.required_bars for spec in FEATURE_SPECS),
    }
    return FeatureBundle(sliced_dates, sliced, latest, warmup)


def sma_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        return out
    rolling = 0.0
    for index, value in enumerate(values):
        rolling += value
        if index >= period:
            rolling -= values[index - period]
        if index >= period - 1:
            out[index] = _clean_number(rolling / period)
    return out


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = _clean_number(current)
    for index in range(period, len(values)):
        current = values[index] * alpha + current * (1 - alpha)
        out[index] = _clean_number(current)
    return out


def _compute_full_series(rows: list[dict[str, Any]]) -> dict[str, list[JsonValue]]:
    n = len(rows)
    opens = [row["open"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    dates = [row["date"] for row in rows]
    series: dict[str, list[JsonValue]] = {spec.key: [None] * n for spec in FEATURE_SPECS}

    _compute_price_and_candles(series, rows)
    _compute_gaps(series, rows)
    _compute_returns(series, closes, dates)

    ma_by_period: dict[int, list[float | None]] = {}
    for period in SMA_PERIODS:
        values = sma_series(closes, period)
        ma_by_period[period] = values
        series[f"ma{period}"] = values

    for period in EMA_PERIODS:
        series[f"ema{period}"] = ema_series(closes, period)

    for period, values in ma_by_period.items():
        series[f"ma{period}_slope"] = _slope_series(values)
        series[f"price_to_ma{period}"] = [
            _percent_change(close, ma)
            for close, ma in zip(closes, values)
        ]

    ma5 = ma_by_period[5]
    ma20 = ma_by_period[20]
    ma60 = ma_by_period[60]
    series["bull_alignment"] = _alignment_series(ma5, ma20, ma60, bullish=True)
    series["bear_alignment"] = _alignment_series(ma5, ma20, ma60, bullish=False)
    series["golden_cross"] = _cross_series(ma20, ma60, upward=True)
    series["death_cross"] = _cross_series(ma20, ma60, upward=False)
    series["golden_cross_short"] = _cross_series(ma5, ma20, upward=True)
    series["death_cross_short"] = _cross_series(ma5, ma20, upward=False)
    _compute_momentum(series, closes)
    _compute_volatility(series, rows)
    _compute_volume(series, rows)
    _compute_rolling_sr(series, rows)
    _compute_breakouts(series, rows)
    _compute_rsi(series, closes)
    _compute_macd(series, closes)
    _compute_kd(series, rows)
    _compute_bollinger(series, closes, ma_by_period[20])
    _compute_trend(series, rows, ma5, ma20, ma60)
    _compute_experimental_layers(series, rows)

    return series


def _compute_price_and_candles(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        open_price = row["open"]
        high = row["high"]
        low = row["low"]
        close = row["close"]
        previous_close = rows[index - 1]["close"] if index > 0 else None
        candle_range = high - low
        body_size = abs(close - open_price)
        upper_shadow = max(0.0, high - max(open_price, close))
        lower_shadow = max(0.0, min(open_price, close) - low)
        body_ratio = body_size / candle_range if candle_range > 0 else None
        upper_ratio = upper_shadow / candle_range if candle_range > 0 else None
        lower_ratio = lower_shadow / candle_range if candle_range > 0 else None

        series["previous_close"][index] = _clean_number(previous_close)
        series["price_change"][index] = _clean_number(close - previous_close) if previous_close else None
        series["price_change_percent"][index] = _percent_change(close, previous_close)
        series["typical_price"][index] = _clean_number((high + low + close) / 3)
        series["weighted_price"][index] = _clean_number((high + low + 2 * close) / 4)
        series["mid_price"][index] = _clean_number((high + low) / 2)
        series["body_size"][index] = _clean_number(body_size)
        series["candle_range"][index] = _clean_number(candle_range)
        series["body_ratio"][index] = _clean_number(body_ratio)
        series["upper_shadow"][index] = _clean_number(upper_shadow)
        series["lower_shadow"][index] = _clean_number(lower_shadow)
        series["upper_shadow_ratio"][index] = _clean_number(upper_ratio)
        series["lower_shadow_ratio"][index] = _clean_number(lower_ratio)
        series["bullish"][index] = close > open_price
        series["bearish"][index] = close < open_price
        series["doji"][index] = None if body_ratio is None else body_ratio < 0.1
        series["long_body"][index] = None if body_ratio is None else body_ratio > 0.7
        series["marubozu"][index] = _all_bool(
            upper_ratio is not None and upper_ratio < 0.05,
            lower_ratio is not None and lower_ratio < 0.05,
            body_ratio is not None and body_ratio > 0.7,
        )

        body_in_upper = candle_range > 0 and min(open_price, close) >= low + candle_range * 0.5
        body_in_lower = candle_range > 0 and max(open_price, close) <= low + candle_range * 0.5
        hammer_shape = _all_bool(
            lower_ratio is not None and lower_ratio >= 0.5,
            upper_ratio is not None and upper_ratio <= 0.15,
            body_in_upper,
        )
        inverted_shape = _all_bool(
            upper_ratio is not None and upper_ratio >= 0.5,
            lower_ratio is not None and lower_ratio <= 0.15,
            body_in_lower,
        )
        series["hammer"][index] = hammer_shape
        series["hanging_man"][index] = hammer_shape
        series["inverted_hammer"][index] = inverted_shape
        series["shooting_star"][index] = inverted_shape
        series["spinning_top"][index] = _all_bool(
            body_ratio is not None and body_ratio < 0.3,
            upper_shadow > body_size,
            lower_shadow > body_size,
        )


def _compute_returns(series: dict[str, list[JsonValue]], closes: list[float], dates: list[str]) -> None:
    for period in RETURN_PERIODS:
        key = f"return_{period}d"
        for index, close in enumerate(closes):
            if index >= period:
                series[key][index] = _percent_change(close, closes[index - period])
    series["return_52w"] = list(series["return_250d"])

    first_close_by_year: dict[int, float] = {}
    for index, (date_text, close) in enumerate(zip(dates, closes)):
        parsed = _parse_iso_date(date_text)
        if parsed is None:
            continue
        first_close_by_year.setdefault(parsed.year, close)
        series["return_ytd"][index] = _percent_change(close, first_close_by_year[parsed.year])


def _compute_gaps(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]], *, fill_window: int = 5) -> None:
    for index in range(1, len(rows)):
        prev = rows[index - 1]
        current = rows[index]
        prev_close = prev["close"]
        gap_up = current["low"] > prev["high"]
        gap_down = current["high"] < prev["low"]
        series["gap_up"][index] = gap_up
        series["gap_down"][index] = gap_down
        series["gap_percent"][index] = _percent_change(current["open"], prev_close)
        if not (gap_up or gap_down):
            series["gap_fill_5d"][index] = False
            continue
        filled_days = None
        for ahead in range(1, fill_window + 1):
            check_index = index + ahead
            if check_index >= len(rows):
                break
            row = rows[check_index]
            if (gap_up and row["low"] <= prev_close) or (gap_down and row["high"] >= prev_close):
                filled_days = ahead
                break
        if index + fill_window < len(rows):
            series["gap_fill_5d"][index] = filled_days is not None
            series["gap_fill_days_5d"][index] = filled_days


def _compute_momentum(series: dict[str, list[JsonValue]], closes: list[float]) -> None:
    for period in MOMENTUM_PERIODS:
        for index, close in enumerate(closes):
            if index < period:
                continue
            previous = closes[index - period]
            series[f"momentum_{period}"][index] = _clean_number(close - previous)
            series[f"roc_{period}"][index] = _percent_change(close, previous)
    roc5 = series["roc_5"]
    for index in range(1, len(closes)):
        current = roc5[index]
        previous = roc5[index - 1]
        if current is not None and previous is not None:
            series["price_acceleration"][index] = _clean_number(float(current) - float(previous))


def _compute_volatility(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    trs: list[float | None] = [None] * len(rows)
    log_returns: list[float | None] = [None] * len(rows)
    for index, row in enumerate(rows):
        high = row["high"]
        low = row["low"]
        previous_close = rows[index - 1]["close"] if index > 0 else None
        daily_range = high - low
        series["daily_range"][index] = _clean_number(daily_range)
        series["daily_range_percent"][index] = _clean_number(daily_range / previous_close * 100) if previous_close else None
        tr = daily_range if previous_close is None else max(daily_range, abs(high - previous_close), abs(low - previous_close))
        trs[index] = tr
        series["tr"][index] = _clean_number(tr)
        if previous_close and previous_close > 0:
            log_returns[index] = math.log(row["close"] / previous_close)
    for period in ATR_PERIODS:
        series[f"atr_{period}"] = _wilder_series(trs, period)
    for period in HV_PERIODS:
        series[f"hv_{period}"] = _hv_series(log_returns, period)
    series["annualized_volatility"] = list(series["hv_20"])


def _compute_volume(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    volumes = [row["volume"] for row in rows]
    for period in VOLUME_MA_PERIODS:
        series[f"volume_ma{period}"] = sma_series(volumes, period)
    volume_ma20 = series["volume_ma20"]
    obv_values: list[float | None] = [None] * len(rows)
    obv = 0.0
    for index, row in enumerate(rows):
        if index > 0:
            if row["close"] > rows[index - 1]["close"]:
                obv += row["volume"]
            elif row["close"] < rows[index - 1]["close"]:
                obv -= row["volume"]
        obv_values[index] = _clean_number(obv)
        ma20 = volume_ma20[index]
        if ma20:
            ratio = row["volume"] / float(ma20)
            series["volume_ratio"][index] = _clean_number(ratio)
            series["volume_spike"][index] = ratio >= 2
        if index >= 19:
            sample = volumes[index - 19 : index + 1]
            series["new_volume_high_20"][index] = row["volume"] >= max(sample)
            series["new_volume_low_20"][index] = row["volume"] <= min(sample)
        if index > 0:
            price_up = row["close"] > rows[index - 1]["close"]
            price_down = row["close"] < rows[index - 1]["close"]
            vol_up = row["volume"] > rows[index - 1]["volume"]
            vol_down = row["volume"] < rows[index - 1]["volume"]
            series["price_up_volume_up"][index] = price_up and vol_up
            series["price_up_volume_down"][index] = price_up and vol_down
            series["price_down_volume_up"][index] = price_down and vol_up
            series["price_down_volume_down"][index] = price_down and vol_down
    series["obv"] = obv_values
    obv_ma5 = sma_series([float(v or 0) for v in obv_values], 5)
    series["volume_trend"] = _slope_series(obv_ma5)


def _compute_rolling_sr(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    for period in ROLLING_SR_PERIODS:
        high_series = _rolling_extreme(highs, period, max)
        low_series = _rolling_extreme(lows, period, min)
        series[f"high_{period}"] = high_series
        series[f"low_{period}"] = low_series
        for index, close in enumerate(closes):
            high = high_series[index]
            low = low_series[index]
            series[f"distance_to_high_{period}"][index] = _percent_change(close, high)
            series[f"distance_to_low_{period}"][index] = _percent_change(close, low)
    series["distance_to_52w_high"] = list(series["distance_to_high_250"])
    series["distance_to_52w_low"] = list(series["distance_to_low_250"])


def _compute_breakouts(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    for period in BREAKOUT_PERIODS:
        for index, close in enumerate(closes):
            if index < period:
                continue
            previous_high = max(highs[index - period : index])
            previous_low = min(lows[index - period : index])
            series[f"breakout_{period}"][index] = close > previous_high
            series[f"breakdown_{period}"][index] = close < previous_low
            series[f"breakout_strength_{period}"][index] = _percent_change(close, previous_high)


def _compute_rsi(series: dict[str, list[JsonValue]], closes: list[float]) -> None:
    for period in RSI_PERIODS:
        series[f"rsi_{period}"] = _rsi_series(closes, period)


def _compute_macd(series: dict[str, list[JsonValue]], closes: list[float]) -> None:
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd = [
        _clean_number(a - b) if a is not None and b is not None else None
        for a, b in zip(ema12, ema26)
    ]
    signal = _ema_optional(macd, 9)
    histogram = [
        _clean_number(a - b) if a is not None and b is not None else None
        for a, b in zip(macd, signal)
    ]
    series["macd"] = macd
    series["macd_signal"] = signal
    series["macd_histogram"] = histogram
    series["macd_golden_cross"] = _cross_series(macd, signal, upward=True)
    series["macd_dead_cross"] = _cross_series(macd, signal, upward=False)


def _compute_kd(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]], period: int = 9) -> None:
    k_values: list[float | None] = [None] * len(rows)
    d_values: list[float | None] = [None] * len(rows)
    j_values: list[float | None] = [None] * len(rows)
    if len(rows) < period:
        return
    k = 50.0
    d = 50.0
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    for index in range(period - 1, len(rows)):
        window_low = min(lows[index - period + 1 : index + 1])
        window_high = max(highs[index - period + 1 : index + 1])
        rsv = 50.0 if window_high == window_low else (closes[index] - window_low) / (window_high - window_low) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
        k_values[index] = _clean_number(k)
        d_values[index] = _clean_number(d)
        j_values[index] = _clean_number(3 * k - 2 * d)
    series["kd_k"] = k_values
    series["kd_d"] = d_values
    series["kd_j"] = j_values
    series["kd_golden_cross"] = _cross_series(k_values, d_values, upward=True)
    series["kd_dead_cross"] = _cross_series(k_values, d_values, upward=False)


def _compute_bollinger(series: dict[str, list[JsonValue]], closes: list[float], ma20: list[float | None]) -> None:
    stdev20 = _std_series(closes, 20)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    width: list[float | None] = [None] * len(closes)
    position: list[float | None] = [None] * len(closes)
    breakout: list[bool | None] = [None] * len(closes)
    for index, close in enumerate(closes):
        mid = ma20[index]
        std = stdev20[index]
        if mid is None or std is None:
            continue
        up = mid + 2 * std
        lo = mid - 2 * std
        upper[index] = _clean_number(up)
        lower[index] = _clean_number(lo)
        width[index] = _clean_number((up - lo) / mid) if mid else None
        position[index] = _clean_number((close - lo) / (up - lo)) if up != lo else None
        breakout[index] = close > up or close < lo
    series["bb_middle"] = list(ma20)
    series["bb_upper"] = upper
    series["bb_lower"] = lower
    series["bb_width"] = width
    series["bb_position"] = position
    series["bb_breakout"] = breakout
    squeeze: list[bool | None] = [None] * len(closes)
    for index, value in enumerate(width):
        if value is None or index < 119:
            continue
        sample = [v for v in width[index - 119 : index + 1] if v is not None]
        if sample:
            threshold = sorted(sample)[max(0, int(len(sample) * 0.1) - 1)]
            squeeze[index] = value <= threshold
    series["bb_squeeze"] = squeeze


def _compute_trend(
    series: dict[str, list[JsonValue]],
    rows: list[dict[str, Any]],
    ma5: list[float | None],
    ma20: list[float | None],
    ma60: list[float | None],
) -> None:
    directions: list[str | None] = [None] * len(rows)
    durations: list[int | None] = [None] * len(rows)
    ma60_slope = series["ma60_slope"]
    current_dir = None
    current_len = 0
    for index in range(len(rows)):
        direction = None
        if ma5[index] is not None and ma20[index] is not None and ma60[index] is not None and ma60_slope[index] is not None:
            if bool(series["bull_alignment"][index]) and float(ma60_slope[index]) > 0:
                direction = "多"
            elif bool(series["bear_alignment"][index]) and float(ma60_slope[index]) < 0:
                direction = "空"
            else:
                direction = "盤整"
        directions[index] = direction
        if direction is None:
            current_dir = None
            current_len = 0
        elif direction == current_dir:
            current_len += 1
        else:
            current_dir = direction
            current_len = 1
        durations[index] = current_len if direction is not None else None
    series["trend_direction"] = directions
    series["trend_duration"] = durations
    series["trend_strength"] = _adx_series(rows, 14)
    pivots = _latest_pivot_flags(rows)
    for key, value in pivots.items():
        series[key][-1] = value


def _compute_experimental_layers(series: dict[str, list[JsonValue]], rows: list[dict[str, Any]]) -> None:
    patterns = detect_patterns(rows)
    for key, payload in patterns.items():
        if key in series and series[key]:
            series[key][-1] = payload
    scores = compute_scores(series)
    for key, payload in scores.items():
        if key in series and series[key]:
            series[key][-1] = payload


def _slope_series(values: list[float | None], lag: int = SLOPE_LAG) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for index, value in enumerate(values):
        if index < lag:
            continue
        out[index] = _percent_change(value, values[index - lag])
    return out


def _alignment_series(
    short: list[float | None],
    middle: list[float | None],
    long: list[float | None],
    *,
    bullish: bool,
) -> list[bool | None]:
    out: list[bool | None] = []
    for s, m, l in zip(short, middle, long):
        if s is None or m is None or l is None:
            out.append(None)
        elif bullish:
            out.append(s > m > l)
        else:
            out.append(s < m < l)
    return out


def _cross_series(
    short: list[float | None],
    long: list[float | None],
    *,
    upward: bool,
) -> list[bool | None]:
    out: list[bool | None] = [None] * len(short)
    for index in range(1, len(short)):
        prev_short = short[index - 1]
        prev_long = long[index - 1]
        current_short = short[index]
        current_long = long[index]
        if prev_short is None or prev_long is None or current_short is None or current_long is None:
            continue
        if upward:
            out[index] = prev_short <= prev_long and current_short > current_long
        else:
            out[index] = prev_short >= prev_long and current_short < current_long
    return out


def _rolling_extreme(values: list[float], period: int, fn: Any) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        out[index] = _clean_number(fn(values[index - period + 1 : index + 1]))
    return out


def _std_series(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        sample = values[index - period + 1 : index + 1]
        mean = sum(sample) / period
        variance = sum((value - mean) ** 2 for value in sample) / period
        out[index] = _clean_number(math.sqrt(variance))
    return out


def _wilder_series(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    clean = [value for value in values[:period] if value is not None]
    if len(clean) < period:
        start = next((i for i in range(len(values) - period + 1) if all(v is not None for v in values[i : i + period])), None)
        if start is None:
            return out
    else:
        start = 0
    seed = sum(float(v) for v in values[start : start + period] if v is not None) / period
    seed_index = start + period - 1
    out[seed_index] = _clean_number(seed)
    current = seed
    for index in range(seed_index + 1, len(values)):
        value = values[index]
        if value is None:
            continue
        current = (current * (period - 1) + float(value)) / period
        out[index] = _clean_number(current)
    return out


def _hv_series(log_returns: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(log_returns)
    for index in range(period, len(log_returns)):
        sample = log_returns[index - period + 1 : index + 1]
        if any(value is None for value in sample):
            continue
        numbers = [float(value) for value in sample if value is not None]
        mean = sum(numbers) / period
        variance = sum((value - mean) ** 2 for value in numbers) / period
        out[index] = _clean_number(math.sqrt(variance) * math.sqrt(252) * 100)
    return out


def _rsi_series(closes: list[float], period: int) -> list[float | None]:
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
    return [_clean_number(value) for value in out]


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _ema_optional(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    start = next((i for i in range(len(values) - period + 1) if all(v is not None for v in values[i : i + period])), None)
    if start is None:
        return out
    current = sum(float(v) for v in values[start : start + period] if v is not None) / period
    index = start + period - 1
    out[index] = _clean_number(current)
    alpha = 2 / (period + 1)
    for index in range(index + 1, len(values)):
        value = values[index]
        if value is None:
            continue
        current = float(value) * alpha + current * (1 - alpha)
        out[index] = _clean_number(current)
    return out


def _adx_series(rows: list[dict[str, Any]], period: int) -> list[float | None]:
    n = len(rows)
    plus_dm: list[float | None] = [None] * n
    minus_dm: list[float | None] = [None] * n
    tr: list[float | None] = [None] * n
    for index in range(1, n):
        high = rows[index]["high"]
        low = rows[index]["low"]
        prev_high = rows[index - 1]["high"]
        prev_low = rows[index - 1]["low"]
        prev_close = rows[index - 1]["close"]
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0
        tr[index] = max(high - low, abs(high - prev_close), abs(low - prev_close))
    atr = _wilder_series(tr, period)
    plus_smoothed = _wilder_series(plus_dm, period)
    minus_smoothed = _wilder_series(minus_dm, period)
    dx: list[float | None] = [None] * n
    for index in range(n):
        if atr[index] in (None, 0) or plus_smoothed[index] is None or minus_smoothed[index] is None:
            continue
        plus_di = 100 * float(plus_smoothed[index]) / float(atr[index])
        minus_di = 100 * float(minus_smoothed[index]) / float(atr[index])
        denom = plus_di + minus_di
        dx[index] = 0.0 if denom == 0 else abs(plus_di - minus_di) / denom * 100
    return _wilder_series(dx, period)


def _latest_pivot_flags(rows: list[dict[str, Any]]) -> dict[str, bool | None]:
    from app.analyze.levels import swing_pivot_points

    if len(rows) < 12:
        return {"higher_high": None, "higher_low": None, "lower_high": None, "lower_low": None}
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    pivot_highs, pivot_lows = swing_pivot_points(highs, lows, 3, include_terminal=True)
    result: dict[str, bool | None] = {"higher_high": None, "higher_low": None, "lower_high": None, "lower_low": None}
    if len(pivot_highs) >= 2:
        prev, current = pivot_highs[-2][1], pivot_highs[-1][1]
        result["higher_high"] = current > prev
        result["lower_high"] = current < prev
    if len(pivot_lows) >= 2:
        prev, current = pivot_lows[-2][1], pivot_lows[-1][1]
        result["higher_low"] = current > prev
        result["lower_low"] = current < prev
    return result


def _empty_bundle(*, input_rows: int) -> FeatureBundle:
    empty_series = {spec.key: [] for spec in FEATURE_SPECS}
    return FeatureBundle(
        dates=[],
        series=empty_series,
        latest={spec.key: None for spec in FEATURE_SPECS},
        warmup={
            "input_rows": input_rows,
            "visible_rows": 0,
            "warmup_rows": 0,
            "input_start_date": None,
            "input_end_date": None,
            "visible_start_date": None,
            "visible_end_date": None,
            "longest_required_bars": max(spec.required_bars for spec in FEATURE_SPECS),
        },
    )


def _valid_price_rows(prices: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(prices or []):
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
        if open_price <= 0 or open_price < low or open_price > high:
            continue
        if volume is None:
            volume = 0.0
        if volume == 0 and open_price == high == low == close:
            continue
        rows.append(
            {
                "date": _date_text(_get(item, "date")) or str(index),
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


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _percent_change(current: float | None, base: float | None) -> float | None:
    if current is None or base is None or base == 0:
        return None
    return _clean_number((current / base - 1) * 100)


def _clean_number(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    rounded = round(float(value), 6)
    return 0.0 if rounded == -0.0 else rounded


def _all_bool(*values: bool) -> bool:
    return all(values)
