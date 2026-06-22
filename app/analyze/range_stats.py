from __future__ import annotations

import math
import statistics
from typing import Any


def compute_range_stats(prices: list[Any], start_idx: int, end_idx: int) -> dict[str, object]:
    """Compute factual statistics for an inclusive price range.

    The function keeps the input order. It does not infer direction, advice, or
    future movement; it only summarizes the selected historical rows.
    """
    rows = list(prices or [])
    if not rows:
        return {"available": False, "reason": "no_prices"}
    start = max(0, min(int(start_idx), len(rows) - 1))
    end = max(0, min(int(end_idx), len(rows) - 1))
    if start > end:
        start, end = end, start
    selected = rows[start : end + 1]
    if not selected:
        return {"available": False, "reason": "empty_range"}

    start_price = _number(_field(selected[0], "close"))
    end_price = _number(_field(selected[-1], "close"))
    highs = [_number(_field(item, "high")) for item in selected]
    lows = [_number(_field(item, "low")) for item in selected]
    volumes = [_number(_field(item, "volume")) for item in selected]
    closes = [_number(_field(item, "close")) for item in selected]

    highest = _safe_max(highs)
    lowest = _safe_min(lows)
    valid_volumes = [v for v in volumes if v is not None]
    average_volume = sum(valid_volumes) / len(valid_volumes) if valid_volumes else None
    price_change = (
        end_price - start_price
        if start_price is not None and end_price is not None
        else None
    )
    price_change_percent = (
        (price_change / start_price) * 100
        if price_change is not None and start_price
        else None
    )
    amplitude_percent = (
        ((highest - lowest) / start_price) * 100
        if highest is not None and lowest is not None and start_price
        else None
    )

    returns: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous and current is not None:
            returns.append((current / previous) - 1)
    annualized_volatility_percent = (
        statistics.stdev(returns) * math.sqrt(252) * 100
        if len(returns) >= 2
        else None
    )

    vwap = _vwap(selected)

    return {
        "available": True,
        "start_index": start,
        "end_index": end,
        "start_date": _field(selected[0], "date"),
        "end_date": _field(selected[-1], "date"),
        "trading_days": len(selected),
        "start_price": start_price,
        "end_price": end_price,
        "price_change": price_change,
        "price_change_percent": price_change_percent,
        "highest": highest,
        "lowest": lowest,
        "amplitude_percent": amplitude_percent,
        "average_volume": average_volume,
        "annualized_volatility_percent": annualized_volatility_percent,
        "vwap": vwap,
    }


def _vwap(rows: list[Any]) -> float | None:
    trade_value_sum = 0.0
    trade_volume_sum = 0.0
    has_trade_value = False
    fallback_value_sum = 0.0
    fallback_volume_sum = 0.0
    for item in rows:
        volume = _number(_field(item, "volume"))
        close = _number(_field(item, "close"))
        trade_value = _number(_field(item, "trade_value"))
        if volume is not None and volume > 0 and close is not None:
            fallback_value_sum += close * volume
            fallback_volume_sum += volume
        if volume is not None and volume > 0 and trade_value is not None and trade_value > 0:
            has_trade_value = True
            trade_value_sum += trade_value
            trade_volume_sum += volume
    if has_trade_value and trade_volume_sum:
        return trade_value_sum / trade_volume_sum
    if fallback_volume_sum:
        return fallback_value_sum / fallback_volume_sum
    return None


def _field(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _safe_max(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def _safe_min(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return min(valid) if valid else None


computeRangeStats = compute_range_stats
