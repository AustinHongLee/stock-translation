"""Low-confidence chart pattern recognition.

These helpers intentionally return conservative, explainable matches. They are
for visual review only, not trading signals.
"""
from __future__ import annotations

from typing import Any, Sequence

from app.analyze.levels import swing_pivot_points

PATTERN_KEYS = (
    "double_top",
    "double_bottom",
    "head_and_shoulders",
    "inverse_head_and_shoulders",
    "triangle",
    "ascending_triangle",
    "descending_triangle",
    "flag",
    "pennant",
    "cup_and_handle",
)

DISCLAIMER = "自動型態辨識誤判率高，僅供畫面標註與人工複查，不是買賣訊號。"


def detect_patterns(rows: Sequence[dict[str, Any]], *, k: int = 3) -> dict[str, dict[str, Any]]:
    if len(rows) < 30:
        return {key: _empty(key, "資料不足") for key in PATTERN_KEYS}
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    pivot_highs, pivot_lows = swing_pivot_points(highs, lows, k, include_terminal=True)
    result = {key: _empty(key, "低信心，需人工確認") for key in PATTERN_KEYS}
    result["double_top"] = _double_top(pivot_highs, rows)
    result["double_bottom"] = _double_bottom(pivot_lows, rows)
    result["head_and_shoulders"] = _head_shoulders(pivot_highs, rows, inverse=False)
    result["inverse_head_and_shoulders"] = _head_shoulders(pivot_lows, rows, inverse=True)
    result["triangle"] = _triangle(pivot_highs, pivot_lows, rows)
    result["ascending_triangle"] = _ascending_triangle(pivot_highs, pivot_lows, rows)
    result["descending_triangle"] = _descending_triangle(pivot_highs, pivot_lows, rows)
    result["flag"] = _flag(closes, rows)
    result["pennant"] = _pennant(pivot_highs, pivot_lows, rows)
    result["cup_and_handle"] = _cup_and_handle(pivot_highs, pivot_lows, rows)
    return result


def _double_top(pivots: list[tuple[int, float]], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(pivots) < 2:
        return _empty("double_top", "樞紐高點不足")
    a, b = pivots[-2], pivots[-1]
    if _near(a[1], b[1], 0.035) and b[0] - a[0] >= 8:
        return _match("double_top", 42, a[0], b[0], rows, "兩個接近的樞紐高點，僅供人工複查。")
    return _empty("double_top", "未出現兩個接近高點")


def _double_bottom(pivots: list[tuple[int, float]], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(pivots) < 2:
        return _empty("double_bottom", "樞紐低點不足")
    a, b = pivots[-2], pivots[-1]
    if _near(a[1], b[1], 0.035) and b[0] - a[0] >= 8:
        return _match("double_bottom", 42, a[0], b[0], rows, "兩個接近的樞紐低點，僅供人工複查。")
    return _empty("double_bottom", "未出現兩個接近低點")


def _head_shoulders(
    pivots: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
    *,
    inverse: bool,
) -> dict[str, Any]:
    key = "inverse_head_and_shoulders" if inverse else "head_and_shoulders"
    if len(pivots) < 3:
        return _empty(key, "樞紐點不足")
    left, head, right = pivots[-3], pivots[-2], pivots[-1]
    shoulders_close = _near(left[1], right[1], 0.06)
    head_extreme = head[1] < left[1] and head[1] < right[1] if inverse else head[1] > left[1] and head[1] > right[1]
    if shoulders_close and head_extreme:
        return _match(key, 38, left[0], right[0], rows, "三個樞紐近似頭肩結構，低信心。")
    return _empty(key, "未符合頭肩幾何條件")


def _triangle(
    pivot_highs: list[tuple[int, float]],
    pivot_lows: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return _empty("triangle", "樞紐點不足")
    h1, h2 = pivot_highs[-2], pivot_highs[-1]
    l1, l2 = pivot_lows[-2], pivot_lows[-1]
    if h2[1] < h1[1] and l2[1] > l1[1]:
        return _match("triangle", 40, min(h1[0], l1[0]), max(h2[0], l2[0]), rows, "高點降低且低點墊高，疑似收斂。")
    return _empty("triangle", "未見高低點收斂")


def _ascending_triangle(
    pivot_highs: list[tuple[int, float]],
    pivot_lows: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return _empty("ascending_triangle", "樞紐點不足")
    h1, h2 = pivot_highs[-2], pivot_highs[-1]
    l1, l2 = pivot_lows[-2], pivot_lows[-1]
    if _near(h1[1], h2[1], 0.035) and l2[1] > l1[1]:
        return _match("ascending_triangle", 36, min(h1[0], l1[0]), max(h2[0], l2[0]), rows, "高點接近、低點墊高，低信心。")
    return _empty("ascending_triangle", "未符合上升三角條件")


def _descending_triangle(
    pivot_highs: list[tuple[int, float]],
    pivot_lows: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return _empty("descending_triangle", "樞紐點不足")
    h1, h2 = pivot_highs[-2], pivot_highs[-1]
    l1, l2 = pivot_lows[-2], pivot_lows[-1]
    if _near(l1[1], l2[1], 0.035) and h2[1] < h1[1]:
        return _match("descending_triangle", 36, min(h1[0], l1[0]), max(h2[0], l2[0]), rows, "低點接近、高點降低，低信心。")
    return _empty("descending_triangle", "未符合下降三角條件")


def _flag(closes: list[float], rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(closes) < 25:
        return _empty("flag", "資料不足")
    impulse = _pct(closes[-11], closes[-25])
    drift = _pct(closes[-1], closes[-11])
    if abs(impulse) >= 10 and abs(drift) <= 5 and impulse * drift <= 0:
        return _match("flag", 32, len(rows) - 25, len(rows) - 1, rows, "先有急動，再有短期反向整理，低信心。")
    return _empty("flag", "未見急動後整理")


def _pennant(
    pivot_highs: list[tuple[int, float]],
    pivot_lows: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    tri = _triangle(pivot_highs, pivot_lows, rows)
    if tri["matched"] and tri["start_index"] is not None and tri["end_index"] is not None:
        if tri["end_index"] - tri["start_index"] <= 35:
            tri = {**tri, "key": "pennant", "confidence": min(34, tri["confidence"])}
            return tri
    return _empty("pennant", "未見短期收斂旗形")


def _cup_and_handle(
    pivot_highs: list[tuple[int, float]],
    pivot_lows: list[tuple[int, float]],
    rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    if len(pivot_highs) < 2 or not pivot_lows:
        return _empty("cup_and_handle", "樞紐點不足")
    h1, h2 = pivot_highs[-2], pivot_highs[-1]
    lows_between = [p for p in pivot_lows if h1[0] < p[0] < h2[0]]
    if lows_between and _near(h1[1], h2[1], 0.08) and h2[0] - h1[0] >= 25:
        return _match("cup_and_handle", 30, h1[0], h2[0], rows, "兩側高點接近且中間有低點，疑似杯形，低信心。")
    return _empty("cup_and_handle", "未符合杯形幾何條件")


def _match(key: str, confidence: int, start: int, end: int, rows: Sequence[dict[str, Any]], note: str) -> dict[str, Any]:
    return {
        "key": key,
        "matched": True,
        "confidence": confidence,
        "start_index": start,
        "end_index": end,
        "start_date": rows[start].get("date") if 0 <= start < len(rows) else None,
        "end_date": rows[end].get("date") if 0 <= end < len(rows) else None,
        "note": note,
        "disclaimer": DISCLAIMER,
    }


def _empty(key: str, note: str) -> dict[str, Any]:
    return {
        "key": key,
        "matched": False,
        "confidence": 0,
        "start_index": None,
        "end_index": None,
        "start_date": None,
        "end_date": None,
        "note": note,
        "disclaimer": DISCLAIMER,
    }


def _near(a: float, b: float, tolerance: float) -> bool:
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base <= tolerance


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current / previous - 1) * 100
