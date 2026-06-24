"""Structure Fingerprint registry and public payload assembly.

The numeric estimators live in ``structure_metrics``.  This module owns the
product-facing labels, bar mapping, sufficiency rules, and guardrail text.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from app.analyze.structure_metrics import build_structure_fingerprint


TITLE = "結構指紋"
SUBTITLE = "這檔股票現在的性格（結構描述，非預測）"
DISCLAIMER = "結構描述工具 · 描述現在 · 不預測未來 · 非投資建議"
DEFAULT_WINDOW = 250
BAR_MAX = 5

RECOMMENDED_BARS = {
    "hurst_dfa": 250,
    "permutation_entropy": 120,
    "volatility_clustering": 150,
    "spectral_slope": 256,
    "realized_vol_percentile": 60,
}


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    key: str
    source: str
    label: str
    bar_lo: float
    bar_hi: float
    forbidden: str
    overlap_note: str
    glossary_term: str
    locked: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


DIMENSION_SPECS: tuple[DimensionSpec, ...] = (
    DimensionSpec(
        key="memory",
        source="hurst_dfa",
        label="延續性",
        bar_lo=0.3,
        bar_hi=1.0,
        forbidden="不得解讀為後續方向承諾或必然反轉；延續性描述自相關結構，不含方向。",
        overlap_note="與圖上「趨勢強度 ADX」不同：ADX 講趨勢強弱，延續性講序列的自相關結構。",
        glossary_term="延續性",
    ),
    DimensionSpec(
        key="complexity",
        source="permutation_entropy",
        label="複雜度",
        bar_lo=0.4,
        bar_hi=1.0,
        forbidden="低複雜度不等於可預測或可獲利。",
        overlap_note="圖上沒有對應指標，這是新增的描述維度。",
        glossary_term="複雜度",
    ),
    DimensionSpec(
        key="agitation",
        source="volatility_clustering",
        label="波動聚集",
        bar_lo=0.0,
        bar_hi=3.0,
        forbidden="不得解讀為即將出現大幅方向變動；只描述波動的聚集性。",
        overlap_note="與 HV20/ATR 不同：這量化「大波是否成群出現」，不是波動絕對值。",
        glossary_term="波動聚集",
    ),
    DimensionSpec(
        key="chroma",
        source="spectral_slope",
        label="噪音色",
        bar_lo=0.0,
        bar_hi=2.0,
        forbidden="不得當週期或轉折預告。",
        overlap_note="描述「波動的顏色」（白/粉紅/紅），不是方向或週期。",
        glossary_term="噪音色",
    ),
    DimensionSpec(
        key="turbulence",
        source="realized_vol_percentile",
        label="湍流程度",
        bar_lo=0.0,
        bar_hi=100.0,
        forbidden="高波動不等於方向判斷；只描述目前波動相對自身歷史的位置。",
        overlap_note="這是 HV 的「歷史百分位」（跟自己比），不是絕對波動率。",
        glossary_term="湍流程度",
    ),
    DimensionSpec(
        key="synchrony",
        source="",
        label="同步性",
        bar_lo=0.0,
        bar_hi=0.0,
        forbidden="需要跨股資料；個股頁不做同步性判讀。",
        overlap_note="個股看不到同步性，要看市場層級雷達。",
        glossary_term="同步性",
        locked=True,
    ),
)


def bar_level(spec: DimensionSpec, value: float | None) -> int | None:
    if value is None:
        return None
    if spec.bar_hi <= spec.bar_lo:
        return 0
    ratio = (float(value) - spec.bar_lo) / (spec.bar_hi - spec.bar_lo)
    return max(0, min(BAR_MAX, round(ratio * BAR_MAX)))


def sufficiency_grade(bars_available: int) -> str:
    if bars_available >= 256:
        return "high"
    if bars_available >= 150:
        return "medium"
    if bars_available >= 120:
        return "low"
    return "insufficient"


def build_structure_payload(
    closes: Sequence[float],
    *,
    as_of_date: str | None = None,
    window: int = DEFAULT_WINDOW,
) -> dict[str, Any]:
    cleaned = _clean_closes(closes)
    # Spectral slope needs 256 bars, so keep the user-facing 250-day default while
    # allowing the estimator enough bars when they exist.
    calc_window = max(window, max(RECOMMENDED_BARS.values()))
    sample = cleaned[-calc_window:]
    bars_available = len(sample)
    fingerprint = build_structure_fingerprint(sample)
    metrics = fingerprint.get("metrics") if isinstance(fingerprint, dict) else {}
    dimensions = [_dimension_payload(spec, metrics, bars_available) for spec in DIMENSION_SPECS]
    unlocked = [item for item in dimensions if not item.get("locked")]
    return {
        "available": any(bool(item.get("available")) for item in unlocked),
        "as_of_date": as_of_date,
        "window": window,
        "title": TITLE,
        "subtitle": SUBTITLE,
        "disclaimer": DISCLAIMER,
        "sufficiency": {
            "bars_available": bars_available,
            "grade": sufficiency_grade(bars_available),
        },
        "synchrony_locked": True,
        "dimensions": dimensions,
    }


def _dimension_payload(
    spec: DimensionSpec,
    metrics: Any,
    bars_available: int,
) -> dict[str, Any]:
    if spec.locked:
        return {
            "key": spec.key,
            "label": spec.label,
            "locked": True,
            "available": False,
            "bar_level": None,
            "bar_max": BAR_MAX,
            "grade": "locked",
            "summary": "需市場資料（Phase 2）。",
            "forbidden": spec.forbidden,
            "overlap_note": spec.overlap_note,
            "raw": {},
            "method": "Cross-section synchrony, Phase 2",
            "glossary_term": spec.glossary_term,
        }
    snap = metrics.get(spec.source) if isinstance(metrics, dict) else None
    if not isinstance(snap, dict):
        return _unavailable_dimension(spec, bars_available, "缺少估計結果。")
    value = _finite_or_none(snap.get("value"))
    available = bool(snap.get("available")) and value is not None
    grade = _grade_from_snapshot(snap, spec.source, bars_available)
    if not available:
        return _unavailable_dimension(spec, bars_available, str(snap.get("reason") or "資料不足。"), grade=grade)
    return {
        "key": spec.key,
        "label": spec.label,
        "source": spec.source,
        "available": True,
        "bar_level": bar_level(spec, value),
        "bar_max": BAR_MAX,
        "grade": grade,
        "summary": _clean_summary(snap.get("reading") or ""),
        "forbidden": spec.forbidden,
        "overlap_note": spec.overlap_note,
        "raw": {spec.source: value},
        "method": _method_label(spec.source),
        "glossary_term": spec.glossary_term,
    }


def _unavailable_dimension(
    spec: DimensionSpec,
    bars_available: int,
    reason: str,
    *,
    grade: str = "insufficient",
) -> dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label,
        "source": spec.source,
        "available": False,
        "bar_level": None,
        "bar_max": BAR_MAX,
        "grade": grade if grade in {"low", "insufficient"} else "insufficient",
        "summary": f"資料不足：目前 {bars_available} 筆，{_clean_summary(reason)}",
        "forbidden": spec.forbidden,
        "overlap_note": spec.overlap_note,
        "raw": {},
        "method": _method_label(spec.source),
        "glossary_term": spec.glossary_term,
    }


def _clean_closes(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for value in closes or []:
        number = _finite_or_none(value)
        if number is not None and number > 0:
            out.append(number)
    return out


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4)


def _grade_from_snapshot(snap: dict[str, Any], source: str, bars_available: int) -> str:
    if not snap.get("available"):
        return "insufficient"
    recommended = RECOMMENDED_BARS.get(source, 256)
    if bars_available >= recommended:
        return "high"
    if bars_available >= max(60, int(recommended * 0.65)):
        return "medium"
    return "low"


def _clean_summary(value: Any) -> str:
    text = str(value or "").strip()
    replacements = {
        "會" + "跌": "方向判斷",
        "會" + "漲": "方向判斷",
        "買" + "進": "操作",
        "賣" + "出": "操作",
        "目標" + "價": "目標數字",
        "勝" + "率": "統計比例",
        "機" + "率": "比例",
        "看" + "多": "偏正向",
        "看" + "空": "偏負向",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text or "目前沒有可讀摘要。"


def _method_label(source: str) -> str:
    return {
        "hurst_dfa": "DFA-1 on log returns, window=250",
        "permutation_entropy": "Permutation entropy on log returns, d=4",
        "volatility_clustering": "Absolute-return autocorrelation, lags=1..20",
        "spectral_slope": "Log-price spectral slope, mid-frequency band",
        "realized_vol_percentile": "20-day realized volatility percentile",
    }.get(source, "")
