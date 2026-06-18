"""波段支撐/壓力與『接近狀態』偵測（純函數，可單元測試，不碰網路）。

與前端 K 線同一套 swing-pivot 邏輯：在近 window 個交易日找波段轉折點（前後各 k 天都
更高/更低），取最接近現價的『上方壓力』與『下方支撐』，再判斷目前是否接近其中之一。

紅線：只描述價位與接近狀態的事實，不預測股價、不給買賣建議。
"""
from __future__ import annotations

from typing import Any, Sequence

SR_WINDOW = 60       # 波段：近 60 個交易日
SR_PIVOT_K = 3       # 樞紐強度：前後各 3 天
SR_TOLERANCE = 2.0   # 接近門檻（%）


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
    return f if f == f else None  # 排除 NaN


def swing_pivots(highs: Sequence[float], lows: Sequence[float], k: int) -> tuple[list[float], list[float]]:
    pivot_highs: list[float] = []
    pivot_lows: list[float] = []
    n = min(len(highs), len(lows))
    for i in range(k, n - k):
        h = highs[i]
        l = lows[i]
        is_high = all(highs[j] < h for j in range(i - k, i + k + 1) if j != i)
        is_low = all(lows[j] > l for j in range(i - k, i + k + 1) if j != i)
        if is_high:
            pivot_highs.append(h)
        if is_low:
            pivot_lows.append(l)
    return pivot_highs, pivot_lows


def compute_support_resistance(
    prices: Sequence[Any],
    *,
    window: int = SR_WINDOW,
    k: int = SR_PIVOT_K,
    tolerance: float = SR_TOLERANCE,
) -> dict[str, Any]:
    """回傳 {available, support, resistance, dist_support_pct, dist_resistance_pct, status}。

    status: 接近波撐 / 接近波壓 / 區間中 / 資料不足。固定輸入→固定輸出。
    prices 由舊到新（chronological），可為 dict 或物件（有 high/low/close）。
    """
    rows = [p for p in prices if p is not None]
    if len(rows) < 2 * k + 2:
        return {"available": False, "status": "資料不足", "support": None, "resistance": None,
                "dist_support_pct": None, "dist_resistance_pct": None}
    seg = rows[-window:]
    highs = [_f(_get(p, "high")) for p in seg]
    lows = [_f(_get(p, "low")) for p in seg]
    if any(h is None for h in highs) or any(l is None for l in lows):
        highs = [h for h in highs if h is not None]
        lows = [l for l in lows if l is not None]
    close = _f(_get(rows[-1], "close"))
    if close is None or len(highs) < 2 * k + 2 or len(lows) < 2 * k + 2:
        return {"available": False, "status": "資料不足", "support": None, "resistance": None,
                "dist_support_pct": None, "dist_resistance_pct": None}

    pivot_highs, pivot_lows = swing_pivots(highs, lows, k)
    above = [p for p in pivot_highs if p > close]
    resistance = min(above) if above else (max(pivot_highs) if pivot_highs else None)
    below = [p for p in pivot_lows if p < close]
    support = max(below) if below else (min(pivot_lows) if pivot_lows else None)

    dist_r = (resistance - close) / close * 100 if resistance else None
    dist_s = (close - support) / close * 100 if support else None

    status = "區間中"
    near_s = dist_s is not None and dist_s >= 0 and dist_s <= tolerance
    near_r = dist_r is not None and dist_r >= 0 and dist_r <= tolerance
    if near_s and (not near_r or dist_s <= dist_r):
        status = "接近波撐"
    elif near_r:
        status = "接近波壓"

    return {
        "available": True,
        "support": round(support, 2) if support is not None else None,
        "resistance": round(resistance, 2) if resistance is not None else None,
        "dist_support_pct": round(dist_s, 2) if dist_s is not None else None,
        "dist_resistance_pct": round(dist_r, 2) if dist_r is not None else None,
        "status": status,
        "as_of": _date_str(_get(rows[-1], "date")),
    }
