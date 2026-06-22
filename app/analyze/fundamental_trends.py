from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from app.analyze.financial import calculate_financial_metrics


TREND_METRICS: tuple[tuple[str, str], ...] = (
    ("gross_margin_percent", "毛利率"),
    ("operating_margin_percent", "營益率"),
    ("net_margin_percent", "淨利率"),
    ("roe_percent", "單季 ROE"),
)

DISCLAIMER = "多季基本面趨勢只呈現已同步財報的歷史百分比，不預測未來、不構成投資建議。"


def build_fundamental_trends(records: list[Any], *, limit: int = 8) -> dict[str, object]:
    ordered = sorted(
        [item for item in records or [] if _quarter_sort_key(item) is not None],
        key=lambda item: _quarter_sort_key(item) or (0, 0),
    )
    selected = ordered[-max(1, int(limit)) :]
    points = [_point(item) for item in selected]
    series = [_series(key, label, points) for key, label in TREND_METRICS]
    valid_dates = [str(point["source_updated_at"]) for point in points if point.get("source_updated_at")]
    return {
        "available": any(item["available"] for item in series),
        "sample_quarters": len(points),
        "source_updated_at": max(valid_dates) if valid_dates else None,
        "points": points,
        "series": series,
        "disclaimer": DISCLAIMER,
    }


def _point(record: Any) -> dict[str, object]:
    metrics = _metrics(record)
    year = int(_field(record, "year"))
    quarter = int(_field(record, "quarter"))
    return {
        "year": year,
        "quarter": quarter,
        "quarter_label": str(metrics.get("quarter_label") or f"{year}Q{quarter}"),
        "source_updated_at": _date_text(_field(record, "source_updated_at")),
        "gross_margin_percent": _number(metrics.get("gross_margin_percent")),
        "operating_margin_percent": _number(metrics.get("operating_margin_percent")),
        "net_margin_percent": _number(metrics.get("net_margin_percent")),
        "roe_percent": _number(metrics.get("roe_percent")),
    }


def _series(key: str, label: str, points: list[dict[str, object]]) -> dict[str, object]:
    series_points = [
        {
            "quarter_label": point["quarter_label"],
            "source_updated_at": point["source_updated_at"],
            "value": point.get(key),
        }
        for point in points
    ]
    values = [point["value"] for point in series_points if point["value"] is not None]
    latest = values[-1] if values else None
    previous = values[-2] if len(values) >= 2 else None
    change = latest - previous if latest is not None and previous is not None else None
    return {
        "key": key,
        "label": label,
        "unit": "%",
        "available": len(values) >= 2,
        "valid_points": len(values),
        "latest": _number(latest),
        "previous": _number(previous),
        "change": _number(change),
        "points": series_points,
    }


def _metrics(record: Any) -> dict[str, object]:
    if isinstance(record, dict):
        return {
            "quarter_label": record.get("quarter_label"),
            "gross_margin_percent": record.get("gross_margin_percent"),
            "operating_margin_percent": record.get("operating_margin_percent"),
            "net_margin_percent": record.get("net_margin_percent"),
            "roe_percent": record.get("roe_percent"),
        }
    metrics = calculate_financial_metrics(record)
    return {
        "quarter_label": metrics.quarter_label,
        "gross_margin_percent": metrics.gross_margin_percent,
        "operating_margin_percent": metrics.operating_margin_percent,
        "net_margin_percent": metrics.net_margin_percent,
        "roe_percent": metrics.roe_percent,
    }


def _quarter_sort_key(record: Any) -> tuple[int, int] | None:
    try:
        year = int(_field(record, "year"))
        quarter = int(_field(record, "quarter"))
    except (TypeError, ValueError):
        return None
    if quarter < 1 or quarter > 4:
        return None
    return year, quarter


def _field(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
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
