from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta

from app.analyze.assessment import build_assessment
from app.analyze.chart_tour import MAX_BEATS, build_chart_tour
from app.analyze.historical_frequency import build_historical_frequency_report
from app.analyze.indicators import compute_features
from app.analyze.relationships import build_relationships_payload
from app.analyze.structure_registry import build_structure_payload


FORBIDDEN_RE = re.compile(
    r"會漲到|會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|前兆|買訊|賣訊|"
    r"Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price",
    re.IGNORECASE,
)


def _sample_prices(days: int = 180) -> list[dict[str, object]]:
    start = date(2025, 10, 1)
    rows: list[dict[str, object]] = []
    for index in range(days):
        wave = math.sin(index / 8) * 4
        drift = index * 0.18
        close = 100 + drift + wave
        if index in {55, 93, 137}:
            close += 4.5
        open_price = close - (1.8 if index in {55, 137} else 0.35)
        high = max(open_price, close) + 1.1
        low = min(open_price, close) - 1.0
        volume = 1800 + (index % 9) * 80 + (2200 if index in {55, 137} else 0)
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
            }
        )
    return rows


def _payload(*, include_optional: bool = True) -> dict[str, object]:
    prices = _sample_prices()
    features = compute_features(prices).to_json()
    assessment = build_assessment(prices)
    summary = {
        "latest_close": prices[-1]["close"],
        "end_date": prices[-1]["date"],
        "rows": len(prices),
        "price_position": 0.72,
    }
    payload: dict[str, object] = {
        "profile": {"stock_id": "2330", "short_name": "台積電", "name": "台灣積體電路製造"},
        "prices": prices,
        "features": features,
        "summary": summary,
        "assessment": assessment,
    }
    if include_optional:
        payload.update(
            {
                "chips": {
                    "available": True,
                    "days": 24,
                    "latest": {"foreign_net": 100, "trust_net": -50, "dealer_net": 25, "total_net": 75},
                    "sum_20": {"total_net": 880, "days": 20},
                },
                "chips_series": [
                    {"date": str(item["date"]), "total_net": 80 + index}
                    for index, item in enumerate(prices[-24:])
                ],
                "revenue_summary": {
                    "available": True,
                    "facts": [{"label": "年增率", "value": 13.2}],
                },
                "financial_summary": {
                    "available": True,
                    "facts": [{"label": "EPS", "value": 8.4}],
                },
                "structure": build_structure_payload(
                    [float(item["close"]) for item in prices],
                    as_of_date=str(prices[-1]["date"]),
                ),
                "historical_frequency": build_historical_frequency_report(prices),
            }
        )
        payload["relationships"] = build_relationships_payload(payload)
    return payload


def test_chart_tour_builds_guardrailed_beats() -> None:
    tour = build_chart_tour(_payload())

    assert tour["available"] is True
    assert len(tour["beats"]) <= MAX_BEATS
    chapters = [beat["chapter"] for beat in tour["beats"]]
    assert chapters[0] == "intro"
    assert "personality" in chapters
    assert "confirm" in chapters
    assert "trend" in chapters
    assert "levels" in chapters
    assert "watch" in chapters
    assert chapters[-1] == "outro"

    blob = json.dumps(tour, ensure_ascii=False, sort_keys=True)
    assert FORBIDDEN_RE.search(blob) is None
    for beat in tour["beats"]:
        assert beat["narration"]["caution"].strip()
        assert beat["source"]
        assert beat["confidence"] in {"high", "medium", "low"}


def test_watch_beat_is_conditional_and_keeps_next_price_in_targets() -> None:
    tour = build_chart_tour(_payload())
    watch = next(beat for beat in tour["beats"] if beat["chapter"] == "watch")
    text = " ".join(watch["narration"].values())

    assert "如果" in text
    assert "突破" in text or "跌破" in text
    assert "沒突破/跌破前，都只是區間；突破才算數" in text
    assert "會到" not in text
    assert any(target["type"] == "watch_level" and "next_price" in target for target in watch["targets"])


def test_missing_optional_sections_are_skipped_without_errors() -> None:
    tour = build_chart_tour(_payload(include_optional=False))
    chapters = {beat["chapter"] for beat in tour["beats"]}

    assert tour["available"] is True
    assert "chips" not in chapters
    assert "personality" not in chapters
    assert "confirm" not in chapters
    assert "fundamental" not in chapters
    assert "structure" not in chapters
    assert "scenario" not in chapters
    assert len(tour["beats"]) <= MAX_BEATS


def test_each_beat_has_frontend_schema_fields() -> None:
    tour = build_chart_tour(_payload())

    for beat in tour["beats"]:
        assert {"id", "chapter", "title", "targets", "narration", "source", "confidence"} <= set(beat)
        assert {"headline", "why", "caution"} <= set(beat["narration"])
        assert isinstance(beat["targets"], list)
