"""Transparent technical scores for the experimental chart layer.

Scores are 0-100 descriptive readings of current conditions. They are not
probabilities and do not forecast future prices.
"""
from __future__ import annotations

from typing import Any

SCORE_KEYS = (
    "momentum_score",
    "breakout_setup_score",
    "mean_reversion_score",
    "institutional_accumulation_score",
    "crash_risk_score",
)

DISCLAIMER = "分數只描述目前型態強弱，非機率、不預測後續走勢，也不是投資建議。"


def compute_scores(series: dict[str, list[Any]]) -> dict[str, dict[str, Any]]:
    latest = {key: _last(values) for key, values in series.items()}
    roc5 = _num(latest.get("roc_5"))
    roc20 = _num(latest.get("roc_20"))
    rsi14 = _num(latest.get("rsi_14"))
    bias20 = _num(latest.get("price_to_ma20"))
    bb_position = _num(latest.get("bb_position"))
    bb_squeeze = bool(latest.get("bb_squeeze"))
    volume_ratio = _num(latest.get("volume_ratio"))
    near_high = _num(latest.get("distance_to_high_20"))
    obv_trend = _num(latest.get("volume_trend"))
    bear_alignment = bool(latest.get("bear_alignment"))
    breakdown = bool(latest.get("breakdown_20"))
    price_down_volume_up = bool(latest.get("price_down_volume_up"))

    scores = {
        "momentum_score": _score(
            "momentum_score",
            _clamp(50 + (roc5 or 0) * 3 + (roc20 or 0) * 1.2),
            ["ROC5", "ROC20"],
        ),
        "breakout_setup_score": _score(
            "breakout_setup_score",
            _clamp((30 if bb_squeeze else 0) + _proximity_score(near_high) + _volume_score(volume_ratio)),
            ["布林收斂", "貼近20日高", "量比"],
        ),
        "mean_reversion_score": _score(
            "mean_reversion_score",
            _clamp(abs(bias20 or 0) * 4 + _rsi_extreme_score(rsi14)),
            ["MA20乖離", "RSI極端值"],
        ),
        "institutional_accumulation_score": _score(
            "institutional_accumulation_score",
            _clamp(50 + (obv_trend or 0) * 0.8 + _volume_score(volume_ratio) * 0.4),
            ["OBV斜率", "量比"],
        ),
        "crash_risk_score": _score(
            "crash_risk_score",
            _clamp((25 if bear_alignment else 0) + (25 if breakdown else 0) + (20 if price_down_volume_up else 0) + max(0, -(bias20 or 0)) * 2),
            ["空頭排列", "跌破20日前低", "價跌量增", "負乖離"],
        ),
    }
    if bb_position is not None:
        scores["breakout_setup_score"]["inputs"].append("布林位置")
    return scores


def _score(key: str, value: float, inputs: list[str]) -> dict[str, Any]:
    return {
        "key": key,
        "score": round(value, 1),
        "confidence": "experimental",
        "inputs": inputs,
        "label_note": "非機率、不預測",
        "disclaimer": DISCLAIMER,
    }


def _last(values: list[Any]) -> Any:
    return values[-1] if values else None


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _proximity_score(distance_to_high: float | None) -> float:
    if distance_to_high is None:
        return 0.0
    return _clamp(40 - abs(distance_to_high) * 8)


def _volume_score(volume_ratio: float | None) -> float:
    if volume_ratio is None:
        return 0.0
    return _clamp((volume_ratio - 0.8) * 25)


def _rsi_extreme_score(rsi: float | None) -> float:
    if rsi is None:
        return 0.0
    if rsi >= 70:
        return (rsi - 70) * 2
    if rsi <= 30:
        return (30 - rsi) * 2
    return 0.0
