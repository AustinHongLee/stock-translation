from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Iterable

from app.analyze.assessment import build_assessment
from app.analyze.financial import calculate_financial_metrics, financial_title, financial_tone
from app.chips import build_institutional_summary


MIN_COMPARE_STOCKS = 2
MAX_COMPARE_STOCKS = 3
DISCLAIMER = "多股比較只呈現本地已同步資料；只整理價格、法人與體質事實，不預測股價、不構成投資建議。"


def normalize_compare_stock_ids(values: str | Iterable[str]) -> list[str]:
    raw = re.split(r"[\s,，、/|]+", values) if isinstance(values, str) else list(values)
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        stock_id = str(value or "").strip().upper()
        if not stock_id or stock_id in seen:
            continue
        seen.add(stock_id)
        out.append(stock_id)
        if len(out) >= MAX_COMPARE_STOCKS:
            break
    return out


def build_stock_comparison(items: Iterable[dict[str, Any]]) -> dict[str, object]:
    rows = [build_stock_comparison_item(item) for item in items]
    return {
        "count": len(rows),
        "limits": {"min": MIN_COMPARE_STOCKS, "max": MAX_COMPARE_STOCKS},
        "items": rows,
        "disclaimer": DISCLAIMER,
    }


def build_stock_comparison_item(source: dict[str, Any]) -> dict[str, object]:
    stock_id = str(source.get("stock_id") or _profile_field(source.get("profile"), "stock_id") or "").strip()
    profile = _profile_json(source.get("profile"), stock_id)
    prices = _valid_price_rows(source.get("prices") or [])
    latest = prices[-1] if prices else None
    previous = prices[-2] if len(prices) >= 2 else None
    price = _price_signal(prices, latest, previous)
    chips = _chips_signal(build_institutional_summary(source.get("institutional_trades") or []))
    revenue_summary = _revenue_summary(source.get("monthly_revenues") or [])
    financial = _financial_signal(source.get("financial_statements") or [])
    assessment = _assessment_signal(
        build_assessment(
            [_price_json(item) for item in prices],
            chips=chips["raw_summary"] if chips["available"] else None,
            revenue_summary=revenue_summary if revenue_summary.get("available") else None,
        )
    )
    chips.pop("raw_summary", None)
    return {
        "stock_id": stock_id,
        "profile": profile,
        "price": price,
        "chips": chips,
        "assessment": assessment,
        "financial": financial,
        "data_dates": {
            "price": price["date"],
            "chips": chips["as_of"],
            "revenue": revenue_summary.get("source_date"),
            "financial": financial.get("source_date"),
        },
    }


def _price_signal(rows: list[Any], latest: Any, previous: Any) -> dict[str, object]:
    close = _number(_field(latest, "close")) if latest is not None else None
    change = _latest_change(latest, previous)
    highs = [_number(_field(item, "high")) for item in rows]
    lows = [_number(_field(item, "low")) for item in rows]
    highs = [item for item in highs if item is not None]
    lows = [item for item in lows if item is not None]
    window_high = max(highs) if highs else None
    window_low = min(lows) if lows else None
    position_percent = None
    if close is not None and window_high is not None and window_low is not None and window_high > window_low:
        position_percent = round(((close - window_low) / (window_high - window_low)) * 100, 2)
    return {
        "date": _date_text(_field(latest, "date")) if latest is not None else None,
        "latest_close": close,
        "change": change,
        "change_percent": _change_percent(change, previous),
        "rows": len(rows),
        "window_high": window_high,
        "window_low": window_low,
        "window_position_percent": position_percent,
    }


def _chips_signal(summary: dict[str, Any]) -> dict[str, object]:
    if not summary.get("available"):
        return {
            "available": False,
            "level": "資料不足",
            "tone": "unknown",
            "as_of": None,
            "sum_20_total": None,
            "sum_20_lots": None,
            "latest_total": None,
            "headline": summary.get("headline"),
            "raw_summary": summary,
        }
    sum_20 = summary.get("sum_20") or {}
    total = _int_or_none(sum_20.get("total_net"))
    level = str(summary.get("level") or "無")
    return {
        "available": True,
        "level": level,
        "tone": "caution" if level in {"留意", "注意", "警戒"} else "neutral",
        "as_of": summary.get("as_of"),
        "days": sum_20.get("days"),
        "sum_20_total": total,
        "sum_20_lots": _lots(total),
        "latest_total": _int_or_none((summary.get("latest") or {}).get("total_net")),
        "headline": summary.get("headline"),
        "raw_summary": summary,
    }


def _assessment_signal(assessment: dict[str, Any]) -> dict[str, object]:
    counts = assessment.get("counts") or {}
    bull = int(counts.get("bull") or 0)
    bear = int(counts.get("bear") or 0)
    neutral = int(counts.get("neutral") or 0)
    if not assessment.get("available"):
        label = "資料不足"
        tone = "unknown"
    elif bull >= bear + 2:
        label = "體質偏多"
        tone = "positive"
    elif bear >= bull + 2:
        label = "體質留意"
        tone = "caution"
    else:
        label = "體質中性"
        tone = "neutral"
    return {
        "available": bool(assessment.get("available")),
        "label": label,
        "tone": tone,
        "bull": bull,
        "bear": bear,
        "neutral": neutral,
        "summary": assessment.get("summary"),
    }


def _financial_signal(statements: list[Any]) -> dict[str, object]:
    items = sorted(
        [item for item in statements or [] if item is not None],
        key=lambda item: (int(_field(item, "year") or 0), int(_field(item, "quarter") or 0)),
        reverse=True,
    )
    if not items:
        return {
            "available": False,
            "quarter": None,
            "eps": None,
            "roe_percent": None,
            "net_margin_percent": None,
            "tone": "unknown",
            "title": "財報待補",
            "source_date": None,
        }
    latest = items[0]
    metrics = calculate_financial_metrics(latest)
    return {
        "available": True,
        "quarter": metrics.quarter_label,
        "eps": metrics.eps,
        "roe_percent": metrics.roe_percent,
        "net_margin_percent": metrics.net_margin_percent,
        "tone": financial_tone(metrics),
        "title": financial_title(metrics),
        "source_date": _date_text(_field(latest, "source_updated_at")),
    }


def _revenue_summary(records: list[Any]) -> dict[str, object]:
    items = sorted(
        [item for item in records or [] if item is not None],
        key=lambda item: str(_field(item, "year_month") or ""),
        reverse=True,
    )
    if not items:
        return {"available": False, "facts": [], "source_date": None}
    latest = items[0]
    yoy = _number(_field(latest, "yoy_percent"))
    return {
        "available": yoy is not None,
        "facts": [{"label": "年增率", "value": yoy}],
        "source_date": _date_text(_field(latest, "source_updated_at")) or _field(latest, "year_month"),
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


def _profile_json(profile: Any, stock_id: str) -> dict[str, object]:
    return {
        "stock_id": _profile_field(profile, "stock_id") or stock_id,
        "name": _profile_field(profile, "name") or "",
        "short_name": _profile_field(profile, "short_name") or _profile_field(profile, "name") or stock_id,
        "market": _profile_field(profile, "market") or "TWSE",
    }


def _profile_field(profile: Any, key: str) -> Any:
    if profile is None:
        return None
    if isinstance(profile, dict):
        return profile.get(key)
    return getattr(profile, key, None)


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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _lots(value: int | None) -> int | None:
    if value is None:
        return None
    return int(round(value / 1000))
