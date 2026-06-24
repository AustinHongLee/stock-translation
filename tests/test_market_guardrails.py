from __future__ import annotations

import json
import math
import re
from pathlib import Path

from app.analyze.cross_section import ReturnsMatrix
from app.analyze.market_structure import (
    DISCLAIMER,
    SUBTITLE,
    TITLE,
    build_market_radar_metrics,
)
from app.glossary.service import load_glossary


MARKET_FORBIDDEN_RE = re.compile(
    r"會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊|前兆|"
    r"Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price",
    re.IGNORECASE,
)


def _assert_clean(value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert MARKET_FORBIDDEN_RE.search(text) is None


def _market_matrix() -> ReturnsMatrix:
    stock_ids = [str(1000 + idx) for idx in range(36)]
    dates = [f"2026-03-{idx + 1:02d}" for idx in range(70)]
    rows: list[list[float]] = []
    for day_idx in range(len(dates)):
        rows.append([
            0.001 * math.sin(day_idx / 5 + stock_idx * 0.17)
            + 0.0004 * math.cos(day_idx / 11)
            + ((stock_idx % 5) - 2) * 0.00005
            for stock_idx in range(len(stock_ids))
        ])
    return ReturnsMatrix(stock_ids=stock_ids, dates=dates, returns=rows)


def test_market_radar_metric_copy_has_no_direction_or_trigger_language() -> None:
    payload = {
        "title": TITLE,
        "subtitle": SUBTITLE,
        "disclaimer": DISCLAIMER,
        "metrics": build_market_radar_metrics(_market_matrix()),
    }

    _assert_clean(payload)
    assert [metric["label"] for metric in payload["metrics"]] == ["市場波動(分化)", "羊群程度", "同步度"]
    assert all(metric["forbidden"] for metric in payload["metrics"])


def test_market_radar_html_block_has_no_direction_or_trigger_language() -> None:
    html = Path("app/ui/static/index.html").read_text(encoding="utf-8")
    start = html.index('id="marketRadarPanel"')
    end = html.index('id="screenerSnapshotPanel"')

    _assert_clean(html[start:end])
    assert "市場心智雷達" in html[start:end]
    assert "收盤快照排行" not in html[start:end]


def test_market_radar_glossary_terms_are_descriptive_only() -> None:
    entries = {entry.term: entry.to_json() for entry in load_glossary()}
    selected = [entries["市場波動(分化)"], entries["羊群程度"], entries["同步度"]]

    _assert_clean(selected)
    for entry in selected:
        assert "這是描述、不是買賣指令" in str(entry["how_to_read"])
