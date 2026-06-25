from __future__ import annotations

import json
import re

from app.analyze.chart_tour import build_chart_tour
from app.analyze.relationships import build_relationships_payload
from tests.test_relationships import _payload


FORBIDDEN_RE = re.compile(
    r"會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊|前兆|"
    r"猜測|預測|預估會|未來會|接下來會漲|接下來會跌|"
    r"Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price|forecast|predict",
    re.IGNORECASE,
)

LAYER0_RE = re.compile(r"\d|%|MA|EMA|MACD|KD|RSI|OBV|量比|法人|三大法人|布林", re.IGNORECASE)


def test_relationships_output_has_no_forbidden_language() -> None:
    payload = build_relationships_payload(_payload())
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert FORBIDDEN_RE.search(blob) is None
    for item in payload["items"]:
        assert item["forbidden"].strip()
        assert item["narration"]["plain"].strip()
        assert LAYER0_RE.search(item["narration"]["plain"]) is None


def test_confirm_items_are_descriptive_not_directional_promises() -> None:
    payload = build_relationships_payload(_payload())
    confirms = [item for item in payload["items"] if item["group"] == "confirm"]

    assert confirms
    for item in confirms:
        text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        assert "扎實" in item["narration"]["plain"] or "整理" in item["narration"]["plain"]
        assert FORBIDDEN_RE.search(text) is None


def test_missing_sources_degrade_without_exceptions() -> None:
    payload = _payload(institutional=[], structure={"available": False, "dimensions": []})
    payload["features"] = {"available": True, "latest": {}, "series": {}}

    result = build_relationships_payload(payload)

    assert result["available"] is True
    assert result["readability"]["level"] == "medium"
    confirm = next(item for item in result["items"] if item["key"] == "confirm_5d")
    assert "缺少其他來源確認" in confirm["narration"]["plain"]
    assert confirm["reliability"] == "medium"


def test_relationship_beats_in_chart_tour_keep_guardrails() -> None:
    payload = _payload()
    payload["relationships"] = build_relationships_payload(payload)
    tour = build_chart_tour(payload)
    relationship_beats = [
        beat
        for beat in tour["beats"]
        if beat["chapter"] in {"personality", "confirm", "derivation", "progression"}
    ]

    assert relationship_beats
    blob = json.dumps(relationship_beats, ensure_ascii=False, sort_keys=True)
    assert FORBIDDEN_RE.search(blob) is None
    for beat in relationship_beats:
        assert LAYER0_RE.search(beat["narration"]["headline"]) is None
