"""歷史 PE / PB 河流圖資料引擎（分析層純函數，可單元測試，不碰網路、不接 AI）。

對齊《14》P2-6：用近 N 年「實際倍數」算百分位，取代「現價 ±20%」的假 band。
作法：用已同步的『每日收盤價』÷『當時可得的近四季 EPS / 每股淨值』還原出歷史
PE / PB 序列，再算百分位區間與「目前倍數落在第幾百分位」。

紅線：只描述「目前倍數在自己歷史的相對位置」這個事實，不說貴/便宜、不預測、不建議。
位階一律中性呈現（UI 不得用紅綠暗示買賣）。
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

# 季報實際公布通常落後季底一段時間；沒有公布日時用此天數估「可得日」，避免未卜先知。
_REPORT_LAG_DAYS = 50
_MIN_SAMPLES = 60  # 樣本太少不出 band（約一季交易日）


@dataclass(frozen=True, slots=True)
class MetricBand:
    available: bool
    current: float | None
    current_percentile: float | None
    p20: float | None
    p50: float | None
    p80: float | None
    low: float | None
    high: float | None
    sample_size: int
    note: str


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _quarter_end(year: int, quarter: int) -> date:
    month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}.get(quarter, (12, 31))
    return date(year, month_end[0], month_end[1])


def _available_from(stmt: Any) -> date | None:
    explicit = _get(stmt, "source_updated_at")
    if isinstance(explicit, date):
        return explicit
    year = _get(stmt, "year")
    quarter = _get(stmt, "quarter")
    if year is None or quarter is None:
        return None
    try:
        return _quarter_end(int(year), int(quarter)) + timedelta(days=_REPORT_LAG_DAYS)
    except (TypeError, ValueError):
        return None


def _ttm_points(financials: Sequence[Any]) -> list[tuple[date, float | None, float | None]]:
    """回傳 (可得日, 近四季 EPS 合計, 當時每股淨值) 由舊到新。"""
    ordered = sorted(
        (f for f in financials if _get(f, "year") is not None and _get(f, "quarter") is not None),
        key=lambda f: (int(_get(f, "year")), int(_get(f, "quarter"))),
    )
    points: list[tuple[date, float | None, float | None]] = []
    for i in range(3, len(ordered)):
        window = ordered[i - 3 : i + 1]
        eps_values = [_get(q, "eps") for q in window]
        ttm_eps = sum(eps_values) if all(v is not None for v in eps_values) else None
        avail = _available_from(ordered[i])
        if avail is None:
            continue
        bvps = _get(ordered[i], "book_value_per_share")
        points.append((avail, ttm_eps, bvps))
    points.sort(key=lambda item: item[0])
    return points


def _percentile(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * (q / 100)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _current_percentile(sorted_vals: list[float], value: float) -> float:
    count = sum(1 for v in sorted_vals if v <= value)
    return count / len(sorted_vals) * 100


def _build_band(values: list[float], kind: str) -> MetricBand:
    clean = [v for v in values if v is not None and v > 0 and math.isfinite(v)]
    if len(clean) < _MIN_SAMPLES:
        return MetricBand(
            available=False, current=None, current_percentile=None,
            p20=None, p50=None, p80=None, low=None, high=None,
            sample_size=len(clean),
            note=f"歷史{kind}樣本不足（{len(clean)} 筆），先不畫區間。",
        )
    current = clean[-1]
    ordered = sorted(clean)
    return MetricBand(
        available=True,
        current=round(current, 2),
        current_percentile=round(_current_percentile(ordered, current), 0),
        p20=round(_percentile(ordered, 20), 2),
        p50=round(_percentile(ordered, 50), 2),
        p80=round(_percentile(ordered, 80), 2),
        low=round(min(ordered), 2),
        high=round(max(ordered), 2),
        sample_size=len(ordered),
        note=f"近 {kind} 由每日收盤價與當時近四季 EPS／每股淨值還原；只反映歷史相對位置。",
    )


def compute_valuation_bands(
    prices: Sequence[Any],
    financials: Sequence[Any],
    *,
    today: date | None = None,
    years: int = 5,
) -> dict[str, Any]:
    """回傳 {"pe": MetricBand-dict, "pb": MetricBand-dict, ...}。固定輸入→固定輸出。"""
    today = today or date.today()
    start = date(today.year - years, today.month, today.day)
    points = _ttm_points(financials)
    avail_dates = [p[0] for p in points]

    pe_pairs: list[tuple[date, float]] = []
    pb_pairs: list[tuple[date, float]] = []
    sorted_prices = _valid_price_points(prices)
    for pdate, close in sorted_prices:
        if pdate < start:
            continue
        idx = bisect_right(avail_dates, pdate) - 1
        if idx < 0:
            continue
        _, ttm_eps, bvps = points[idx]
        if ttm_eps and ttm_eps > 0:
            pe_pairs.append((pdate, close / ttm_eps))
        if bvps and bvps > 0:
            pb_pairs.append((pdate, close / bvps))

    pe = _band_to_dict(_build_band([v for _, v in pe_pairs], "本益比"))
    pb = _band_to_dict(_build_band([v for _, v in pb_pairs], "本淨比"))
    pe["series"] = _downsample_series(pe_pairs) if pe["available"] else []
    pb["series"] = _downsample_series(pb_pairs) if pb["available"] else []
    return {
        "years": years,
        "as_of": today.isoformat(),
        "pe": pe,
        "pb": pb,
        "disclaimer": "本益比／本淨比河流圖只呈現目前倍數在自己近年區間的相對位置，不是估值高低判斷、不預測股價。",
    }


def _downsample_series(pairs: list[tuple[date, float]], max_points: int = 140) -> list[dict[str, Any]]:
    """把每日序列抽稀到 ≤ max_points 點，縮小傳輸量；保留最後一點。"""
    if not pairs:
        return []
    step = max(1, math.ceil(len(pairs) / max_points))
    sampled = pairs[::step]
    if sampled[-1][0] != pairs[-1][0]:
        sampled.append(pairs[-1])
    return [{"date": d.isoformat(), "value": round(v, 2)} for d, v in sampled]


def _valid_price_points(prices: Sequence[Any]) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []
    for item in prices or []:
        pdate = _get(item, "date")
        if not isinstance(pdate, date):
            continue
        close = _positive_float(_get(item, "close"))
        if close is None:
            continue
        open_price = _positive_float(_get(item, "open"))
        high = _positive_float(_get(item, "high"))
        low = _positive_float(_get(item, "low"))
        volume = _finite_float(_get(item, "volume"))
        if (
            volume == 0
            and high is not None
            and low is not None
            and open_price is not None
            and open_price == high == low == close
        ):
            continue
        points.append((pdate, close))
    return sorted(points, key=lambda item: item[0])


def _positive_float(value: Any) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number > 0 else None


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _band_to_dict(band: MetricBand) -> dict[str, Any]:
    return {
        "available": band.available,
        "current": band.current,
        "current_percentile": band.current_percentile,
        "p20": band.p20,
        "p50": band.p50,
        "p80": band.p80,
        "low": band.low,
        "high": band.high,
        "sample_size": band.sample_size,
        "note": band.note,
    }


def position_phrase(percentile: float | None) -> str:
    """把百分位翻成中性白話（不用貴/便宜、不暗示買賣）。"""
    if percentile is None:
        return "目前倍數在近年區間的位置：資料不足"
    pct = round(percentile)
    if pct >= 80:
        zone = "相對高的位置（近年多數時間比現在低）"
    elif pct <= 20:
        zone = "相對低的位置（近年多數時間比現在高）"
    else:
        zone = "近年區間的中段"
    return f"目前倍數約落在近年的第 {pct} 百分位，處於{zone}。這只是相對位置的描述，不是估值高低或買賣判斷。"
