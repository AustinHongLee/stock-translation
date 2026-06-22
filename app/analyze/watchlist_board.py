from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.analyze.assessment import build_assessment
from app.analyze.levels import compute_support_resistance


DISCLAIMER = "自選股看板只整理本地已同步資料；新聞地雷需進個股頁抓取，不預測股價、不構成投資建議。"


def build_watchlist_board_item(
    stock_id: str,
    profile: dict[str, Any] | None,
    prices: list[Any],
    *,
    today: date | None = None,
) -> dict[str, object]:
    rows = _valid_price_rows(prices)
    today = today or date.today()
    latest = rows[-1] if rows else None
    previous = rows[-2] if len(rows) >= 2 else None
    latest_date = _date_text(_field(latest, "date")) if latest is not None else None
    stale_days = _stale_days(latest_date, today)
    change = _latest_change(latest, previous)
    change_percent = _change_percent(change, previous)
    assessment = build_assessment([_price_json(item) for item in rows])
    sr = compute_support_resistance(rows)
    assessment_signal = _assessment_signal(assessment)
    level_signal = _level_signal(sr)
    risk_signal = _risk_signal(
        rows=len(rows),
        stale_days=stale_days,
        assessment_signal=assessment_signal,
        level_signal=level_signal,
    )
    return {
        "stock_id": stock_id,
        "name": (profile or {}).get("short_name") or (profile or {}).get("name") or stock_id,
        "latest": {
            "close": _number(_field(latest, "close")) if latest is not None else None,
            "date": latest_date,
            "change": change,
            "change_percent": change_percent,
        },
        "data": {
            "rows": len(rows),
            "stale_days": stale_days,
        },
        "assessment": assessment_signal,
        "risk": risk_signal,
        "level": level_signal,
        "disclaimer": DISCLAIMER,
    }


def _assessment_signal(assessment: dict[str, Any]) -> dict[str, object]:
    counts = assessment.get("counts") or {}
    bull = int(counts.get("bull") or 0)
    bear = int(counts.get("bear") or 0)
    neutral = int(counts.get("neutral") or 0)
    if bull >= bear + 2:
        label = "體質偏多"
        tone = "positive"
    elif bear >= bull + 2:
        label = "體質留意"
        tone = "caution"
    else:
        label = "體質中性"
        tone = "neutral"
    return {
        "label": label,
        "tone": tone,
        "bull": bull,
        "bear": bear,
        "neutral": neutral,
    }


def _risk_signal(
    *,
    rows: int,
    stale_days: int | None,
    assessment_signal: dict[str, object],
    level_signal: dict[str, object],
) -> dict[str, object]:
    if rows == 0:
        return _risk("資料不足", "unknown", "本地日線不足，先同步資料。")
    if stale_days is None or stale_days > 10:
        return _risk("資料過期", "caution", "本地資料日期偏舊，先同步再看。")
    if assessment_signal.get("tone") == "caution":
        return _risk("體質留意", "caution", "本地體質因子偏空較多，需進個股頁查看細節。")
    if level_signal.get("tone") == "caution":
        return _risk("關卡留意", "caution", "目前接近波段關卡，需進個股頁看 K 線位置。")
    return _risk("本地未見", "neutral", "本地資料未見警戒；新聞風險需進個股頁抓取。")


def _risk(label: str, tone: str, detail: str) -> dict[str, object]:
    return {"label": label, "tone": tone, "detail": detail, "source": "local_only"}


def _level_signal(sr: dict[str, Any]) -> dict[str, object]:
    status = str(sr.get("status") or "資料不足")
    tone = "caution" if status in {"接近波壓", "接近波撐"} else ("unknown" if status == "資料不足" else "neutral")
    return {
        "status": status,
        "tone": tone,
        "support": _number(sr.get("support")),
        "resistance": _number(sr.get("resistance")),
    }


def _valid_price_rows(prices: list[Any]) -> list[Any]:
    rows = [item for item in prices or [] if _positive(_field(item, "close"))]
    return sorted(rows, key=lambda item: str(_field(item, "date") or ""))


def _price_json(item: Any) -> dict[str, object]:
    return {
        "date": _date_text(_field(item, "date")),
        "open": _number(_field(item, "open")),
        "high": _number(_field(item, "high")),
        "low": _number(_field(item, "low")),
        "close": _number(_field(item, "close")),
        "volume": _number(_field(item, "volume")),
    }


def _latest_change(latest: Any, previous: Any) -> float | None:
    if latest is None:
        return None
    explicit = _number(_field(latest, "change"))
    if explicit is not None:
        return explicit
    latest_close = _number(_field(latest, "close"))
    previous_close = _number(_field(previous, "close")) if previous is not None else None
    if latest_close is None or previous_close is None:
        return None
    return round(latest_close - previous_close, 4)


def _change_percent(change: float | None, previous: Any) -> float | None:
    previous_close = _number(_field(previous, "close")) if previous is not None else None
    if change is None or not previous_close:
        return None
    return round((change / previous_close) * 100, 4)


def _stale_days(value: str | None, today: date) -> int | None:
    if not value:
        return None
    try:
        return (today - date.fromisoformat(value)).days
    except ValueError:
        return None


def _field(item: Any, key: str) -> Any:
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _date_text(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return text or None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4)


def _positive(value: Any) -> bool:
    number = _number(value)
    return number is not None and number > 0
