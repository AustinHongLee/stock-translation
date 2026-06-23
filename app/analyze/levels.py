"""波段支撐/壓力與『接近狀態』偵測（純函數，可單元測試，不碰網路）。

與前端 K 線同一套 swing-pivot 邏輯：在近 window 個交易日找波段轉折點（前後各 k 天都
    更高/更低），取最接近現價的『上方壓力』與『下方支撐』，再判斷目前是否接近其中之一。
    若價格已突破所有樞紐高或跌破所有樞紐低，不把錯邊舊關卡硬當壓力/支撐。
    末端轉折會在至少 1 根右側 K 線確認後先納入，並過濾單一長影線噪音。

紅線：只描述價位與接近狀態的事實，不預測股價、不給買賣建議。
"""
from __future__ import annotations

import math
from typing import Any, Sequence

SR_WINDOW = 60       # 波段：近 60 個交易日
SR_PIVOT_K = 3       # 樞紐強度：前後各 3 天
SR_TOLERANCE = 2.0   # 接近門檻（%）
_LIMIT_LOCK_GAP = 0.07
_PIVOT_TOUCH_TOLERANCE = 0.025
_PIVOT_CLOSE_TOLERANCE = 0.03


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _date_str(value: Any) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return value.isoformat() if callable(iso) else str(value)


def _f(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def swing_pivot_points(
    highs: Sequence[float],
    lows: Sequence[float],
    k: int,
    *,
    include_terminal: bool = False,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []
    n = min(len(highs), len(lows))
    for i in range(k, n - k):
        h = highs[i]
        l = lows[i]
        is_high = all(highs[j] < h for j in range(i - k, i + k + 1) if j != i)
        is_low = all(lows[j] > l for j in range(i - k, i + k + 1) if j != i)
        if is_high:
            pivot_highs.append((i, h))
        if is_low:
            pivot_lows.append((i, l))
    if include_terminal:
        terminal_highs, terminal_lows = _terminal_pivot_points(highs, lows, k)
        by_high_index = {idx: value for idx, value in pivot_highs}
        by_low_index = {idx: value for idx, value in pivot_lows}
        by_high_index.update(terminal_highs)
        by_low_index.update(terminal_lows)
        pivot_highs = sorted(by_high_index.items())
        pivot_lows = sorted(by_low_index.items())
    return pivot_highs, pivot_lows


def swing_pivots(highs: Sequence[float], lows: Sequence[float], k: int) -> tuple[list[float], list[float]]:
    pivot_highs, pivot_lows = swing_pivot_points(highs, lows, k)
    return [value for _, value in pivot_highs], [value for _, value in pivot_lows]


def _terminal_pivot_points(
    highs: Sequence[float],
    lows: Sequence[float],
    k: int,
) -> tuple[dict[int, float], dict[int, float]]:
    terminal_highs: dict[int, float] = {}
    terminal_lows: dict[int, float] = {}
    n = min(len(highs), len(lows))
    if n < k + 2:
        return terminal_highs, terminal_lows
    start = max(k, n - k)
    # The latest bar itself has no right-side confirmation; wait for at least
    # one subsequent bar before treating a fresh turn as provisional.
    for i in range(start, n - 1):
        left = range(i - k, i)
        right = range(i + 1, n)
        h = highs[i]
        l = lows[i]
        if all(highs[j] < h for j in left) and all(highs[j] < h for j in right):
            terminal_highs[i] = h
        if all(lows[j] > l for j in left) and all(lows[j] > l for j in right):
            terminal_lows[i] = l
    return terminal_highs, terminal_lows


def _filter_noisy_pivots(
    pivots: list[tuple[int, float]],
    rows: list[dict[str, Any]],
    *,
    side: str,
) -> list[float]:
    return [
        value
        for index, value in pivots
        if _has_nearby_touch(value, rows, side=side)
        or _pivot_close_confirms(rows[index], value, side=side)
    ]


def _has_nearby_touch(level: float, rows: list[dict[str, Any]], *, side: str) -> bool:
    key = "high" if side == "high" else "low"
    touches = 0
    for row in rows:
        value = row[key]
        if level > 0 and abs(value - level) / level <= _PIVOT_TOUCH_TOLERANCE:
            touches += 1
            if touches >= 2:
                return True
    return False


def _pivot_close_confirms(row: dict[str, Any], level: float, *, side: str) -> bool:
    close = row["close"]
    if level <= 0 or close <= 0:
        return False
    if side == "high":
        return (level - close) / level <= _PIVOT_CLOSE_TOLERANCE
    return (close - level) / level <= _PIVOT_CLOSE_TOLERANCE


def compute_support_resistance(
    prices: Sequence[Any],
    *,
    window: int = SR_WINDOW,
    k: int = SR_PIVOT_K,
    tolerance: float = SR_TOLERANCE,
) -> dict[str, Any]:
    """回傳 {available, support, resistance, dist_support_pct, dist_resistance_pct, status}。

    status: 接近波撐 / 接近波壓 / 創區間新高 / 創區間新低 / 支撐上方 / 壓力下方 / 關卡待確認 / 區間中 / 資料不足。
    固定輸入→固定輸出。
    prices 由舊到新（chronological），可為 dict 或物件（有 high/low/close）。
    """
    rows = _valid_price_rows(prices)
    if len(rows) < 2 * k + 2:
        return {"available": False, "status": "資料不足", "support": None, "resistance": None,
                "dist_support_pct": None, "dist_resistance_pct": None}
    seg = _drop_isolated_limit_locks(rows[-window:])
    highs = [p["high"] for p in seg]
    lows = [p["low"] for p in seg]
    close = rows[-1]["close"]
    if len(highs) < 2 * k + 2 or len(lows) < 2 * k + 2:
        return {"available": False, "status": "資料不足", "support": None, "resistance": None,
                "dist_support_pct": None, "dist_resistance_pct": None}

    pivot_high_points, pivot_low_points = swing_pivot_points(highs, lows, k, include_terminal=True)
    pivot_highs = _filter_noisy_pivots(pivot_high_points, seg, side="high")
    pivot_lows = _filter_noisy_pivots(pivot_low_points, seg, side="low")
    above = [p for p in pivot_highs if p > close]
    resistance = min(above) if above else None
    below = [p for p in pivot_lows if p < close]
    support = max(below) if below else None

    dist_r = (resistance - close) / close * 100 if resistance else None
    dist_s = (close - support) / close * 100 if support else None

    status = "區間中"
    near_s = dist_s is not None and dist_s >= 0 and dist_s <= tolerance
    near_r = dist_r is not None and dist_r >= 0 and dist_r <= tolerance
    if pivot_highs and resistance is None and close > max(pivot_highs):
        status = "創區間新高"
    elif pivot_lows and support is None and close < min(pivot_lows):
        status = "創區間新低"
    elif near_s and (not near_r or dist_s <= dist_r):
        status = "接近波撐"
    elif near_r:
        status = "接近波壓"
    elif support is not None and resistance is None:
        status = "支撐上方"
    elif resistance is not None and support is None:
        status = "壓力下方"
    elif support is None and resistance is None:
        status = "關卡待確認"

    return {
        "available": True,
        "support": round(support, 2) if support is not None else None,
        "resistance": round(resistance, 2) if resistance is not None else None,
        "dist_support_pct": round(dist_s, 2) if dist_s is not None else None,
        "dist_resistance_pct": round(dist_r, 2) if dist_r is not None else None,
        "status": status,
        "as_of": _date_str(_get(rows[-1], "date")),
    }


def _valid_price_rows(prices: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in prices or []:
        high = _f(_get(item, "high"))
        low = _f(_get(item, "low"))
        close = _f(_get(item, "close"))
        if high is None or low is None or close is None:
            continue
        if high <= 0 or low <= 0 or close <= 0 or high < low:
            continue
        if close < low or close > high:
            continue
        open_price = _f(_get(item, "open"))
        volume = _f(_get(item, "volume"))
        if volume == 0 and (close if open_price is None else open_price) == high == low == close:
            continue
        rows.append({
            "date": _get(item, "date"),
            "open": open_price if open_price is not None else close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    return rows


def _drop_isolated_limit_locks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 3:
        return rows
    kept: list[dict[str, Any]] = [rows[0]]
    for previous, current, nxt in zip(rows, rows[1:], rows[2:]):
        if not _is_isolated_limit_lock(previous, current, nxt):
            kept.append(current)
    kept.append(rows[-1])
    return kept


def _is_isolated_limit_lock(previous: dict[str, Any], current: dict[str, Any], nxt: dict[str, Any]) -> bool:
    o = current["open"]
    h = current["high"]
    l = current["low"]
    c = current["close"]
    if not (o == h == l == c):
        return False
    prev_close = previous["close"]
    next_close = nxt["close"]
    if prev_close <= 0 or next_close <= 0:
        return False
    above_neighbors = c > prev_close * (1 + _LIMIT_LOCK_GAP) and c > next_close * (1 + _LIMIT_LOCK_GAP)
    below_neighbors = c < prev_close * (1 - _LIMIT_LOCK_GAP) and c < next_close * (1 - _LIMIT_LOCK_GAP)
    return above_neighbors or below_neighbors
