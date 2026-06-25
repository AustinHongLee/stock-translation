"""Experimental technical forecast lab.

This module consumes the already-built stock payload. It does not fetch data,
recompute base indicators, or alter the main stock payload.
"""
from __future__ import annotations

import math
from typing import Any

from app.analyze.historical_frequency import MIN_NORMAL_SAMPLE_COUNT
from app.analyze.relationships import relationship_readability


DISCLAIMER = "技術面推估實驗 · 只用價格資料 · 常常會錯 · 非投資建議"
LIMITATIONS = "此推估只用價格技術面，缺新聞、法人、風險，僅供參考。"
LEAN_BULL = "偏多"
LEAN_NEUTRAL = "中性"
LEAN_BEAR = "偏空"
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def build_forecast_lab(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Build the isolated experimental forecast-lab payload."""
    data = _dict(payload)
    latest = _dict(_dict(data.get("features")).get("latest"))
    prices = _valid_prices(data.get("prices"))
    if not latest or not prices:
        return _unavailable("缺少可用的日線或指標資料")

    score, factors = _technical_score(latest)
    if not factors:
        return _unavailable("目前沒有足夠指標可形成技術面傾向")

    readability = relationship_readability(_dict(data.get("structure")))
    missing = _missing_context(data)
    confidence = _confidence(readability.get("level"), missing)
    scenario, scenario_event, history_ratio = _scenario_from_frequency(data.get("historical_frequency"))

    return {
        "available": True,
        "experimental": True,
        "lean": _lean_from_score(score),
        "lean_score": int(round(score)),
        "factors": factors,
        "scenario": scenario,
        "scenario_event": scenario_event,
        "history_bullish_ratio": history_ratio,
        "confidence": confidence,
        "readability": readability,
        "missing": missing,
        "limitations": LIMITATIONS,
        "disclaimer": DISCLAIMER,
    }


def _technical_score(latest: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    score = 0.0
    factors: list[dict[str, Any]] = []

    ma5 = _number(latest.get("ma5"))
    ma20 = _number(latest.get("ma20"))
    ma60 = _number(latest.get("ma60"))
    if ma5 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma20 > ma60:
            score += _factor(factors, "ma_alignment", "均線排列", 30, "MA5 高於 MA20，MA20 高於 MA60。")
        elif ma5 < ma20 < ma60:
            score += _factor(factors, "ma_alignment", "均線排列", -30, "MA5 低於 MA20，MA20 低於 MA60。")

    close = _number(latest.get("close"))
    if close is not None and ma20 is not None:
        detail = f"收盤 { _fmt(close) }，MA20 { _fmt(ma20) }。"
        score += _factor(factors, "close_vs_ma20", "收盤相對月線", 10 if close > ma20 else -10, detail)

    macd_hist = _number(latest.get("macd_histogram"))
    if macd_hist is not None:
        score += _factor(factors, "macd_histogram", "MACD 柱", 15 if macd_hist > 0 else -15, f"MACD 柱 {_fmt(macd_hist)}。")

    k = _number(latest.get("kd_k"))
    d = _number(latest.get("kd_d"))
    if k is not None and d is not None:
        if k >= 80:
            score += _factor(factors, "kd", "KD 位置", -5, f"K {_fmt(k)}，D {_fmt(d)}，位置偏熱。")
        elif k > d:
            score += _factor(factors, "kd", "KD 位置", 15, f"K {_fmt(k)} 高於 D {_fmt(d)}。")
        elif k < d:
            score += _factor(factors, "kd", "KD 位置", -15, f"K {_fmt(k)} 低於 D {_fmt(d)}。")

    rsi = _number(latest.get("rsi_14"))
    if rsi is not None:
        if 55 <= rsi <= 70:
            score += _factor(factors, "rsi", "RSI 位置", 10, f"RSI14 {_fmt(rsi)}。")
        elif 30 <= rsi <= 45:
            score += _factor(factors, "rsi", "RSI 位置", -10, f"RSI14 {_fmt(rsi)}。")
        elif rsi > 75:
            score += _factor(factors, "rsi", "RSI 位置", -5, f"RSI14 {_fmt(rsi)}，偏熱。")
        elif rsi < 25:
            score += _factor(factors, "rsi", "RSI 位置", 5, f"RSI14 {_fmt(rsi)}，偏冷。")

    roc = _number(latest.get("roc_20"))
    if roc is not None:
        score += _factor(factors, "roc_20", "20日 ROC", 10 if roc > 0 else -10, f"ROC20 {_fmt(roc)}%。")

    return _clamp(score, -100, 100), factors


def _factor(factors: list[dict[str, Any]], key: str, label: str, weight: int, detail: str) -> int:
    if weight == 0:
        return 0
    factors.append(
        {
            "key": key,
            "label": label,
            "dir": "+" if weight > 0 else "-",
            "weight": weight,
            "detail": detail,
        }
    )
    return weight


def _scenario_from_frequency(report_value: Any) -> tuple[dict[str, Any], dict[str, Any] | None, float | None]:
    report = _dict(report_value)
    events = [item for item in report.get("events") or [] if isinstance(item, dict)]
    candidates = [
        event
        for event in events
        if any(_dict(window).get("available") for window in event.get("windows") or [])
    ]
    if not report.get("available") or not candidates:
        return {}, None, None
    event = sorted(
        candidates,
        key=lambda item: (
            0 if item.get("current_match") else 1,
            -int(_number(item.get("completed_sample_count")) or 0),
        ),
    )[0]
    scenario: dict[str, Any] = {}
    bullish_ratio: float | None = None
    for window in event.get("windows") or []:
        stats = _dict(window)
        days = int(_number(stats.get("days")) or 0)
        if days not in {5, 20} or not stats.get("available"):
            continue
        lo = _number(stats.get("p10_return_percent"))
        hi = _number(stats.get("p90_return_percent"))
        if lo is None or hi is None:
            continue
        count = int(_number(stats.get("count")) or 0)
        mid = _number(stats.get("median_return_percent")) if count >= MIN_NORMAL_SAMPLE_COUNT else None
        entry: dict[str, Any] = {
            "lo": _round(lo),
            "hi": _round(hi),
            "count": count,
            "sample_low": count < MIN_NORMAL_SAMPLE_COUNT,
        }
        if mid is not None:
            entry["mid"] = _round(mid)
        p25 = _number(stats.get("p25_return_percent"))
        p75 = _number(stats.get("p75_return_percent"))
        if p25 is not None:
            entry["p25"] = _round(p25)
        if p75 is not None:
            entry["p75"] = _round(p75)
        ratio = _number(stats.get("positive_ratio_percent"))
        if bullish_ratio is None and ratio is not None:
            bullish_ratio = _round(ratio / 100, 3)
        scenario[f"d{days}"] = entry

    scenario_event = {
        "key": event.get("key"),
        "label": event.get("label"),
        "current_match": bool(event.get("current_match")),
        "completed_sample_count": int(_number(event.get("completed_sample_count")) or 0),
    }
    return scenario, scenario_event, bullish_ratio


def _missing_context(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not _has_news_context(payload):
        missing.append("新聞風險")
    chips_rows = [item for item in payload.get("chips_series") or [] if isinstance(item, dict)]
    chips = _dict(payload.get("chips"))
    if not chips_rows and not chips.get("available"):
        missing.append("法人")
    return missing


def _has_news_context(payload: dict[str, Any]) -> bool:
    for key in ("news", "news_payload", "news_risk", "news_summary"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("available"):
            return True
        if isinstance(value, list) and value:
            return True
    return False


def _confidence(level: Any, missing: list[str]) -> str:
    confidence = str(level or "medium")
    if confidence not in CONFIDENCE_ORDER:
        confidence = "medium"
    if missing and CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER["medium"]:
        confidence = "medium"
    return confidence


def _lean_from_score(score: float) -> str:
    if score >= 25:
        return LEAN_BULL
    if score <= -25:
        return LEAN_BEAR
    return LEAN_NEUTRAL


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "experimental": True,
        "reason": reason,
        "lean": LEAN_NEUTRAL,
        "lean_score": 0,
        "factors": [],
        "scenario": {},
        "history_bullish_ratio": None,
        "confidence": "low",
        "missing": ["新聞風險", "法人"],
        "limitations": LIMITATIONS,
        "disclaimer": DISCLAIMER,
    }


def _valid_prices(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        close = _number(item.get("close"))
        if close is None or close <= 0:
            continue
        rows.append(item)
    return rows


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _fmt(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    return f"{number:,.2f}".rstrip("0").rstrip(".")
