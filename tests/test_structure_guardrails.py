from __future__ import annotations

import json
import re

from app.analyze.structure_registry import DIMENSION_SPECS, build_structure_payload
from app.exporters.html_report import build_stock_report_html


STRUCTURE_FORBIDDEN_RE = re.compile(
    r"會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊|"
    r"Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price",
    re.IGNORECASE,
)


def _assert_clean(value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert STRUCTURE_FORBIDDEN_RE.search(text) is None


def test_structure_registry_copy_has_no_direction_or_trade_language() -> None:
    _assert_clean([item.to_json() for item in DIMENSION_SPECS])
    assert all(item.forbidden for item in DIMENSION_SPECS)


def test_structure_payload_has_no_direction_or_trade_language() -> None:
    closes = [100 + i * 0.2 + ((i % 7) - 3) * 0.4 for i in range(320)]
    payload = build_structure_payload(closes, as_of_date="2026-06-22")

    _assert_clean(payload)
    for item in payload["dimensions"]:
        assert item["forbidden"]


def test_structure_report_output_has_no_direction_or_trade_language() -> None:
    payload = {
        "profile": {"stock_id": "2330", "short_name": "台積電", "market": "TWSE"},
        "summary": {"latest_close": 1080, "end_date": "2026-06-22", "rows": 320},
        "price_window": {"actual_end": "2026-06-22"},
        "prices": [{"date": "2026-06-22", "close": 1080, "volume": 1000}],
        "structure": build_structure_payload(
            [100 + i * 0.2 + ((i % 5) - 2) * 0.3 for i in range(320)],
            as_of_date="2026-06-22",
        ),
        "assessment": {"title": "體質總評", "summary": "資料整理中。", "counts": {}, "factors": []},
        "chips": {},
        "valuation": {},
        "report": {"sections": []},
        "annotations": [],
    }
    html = build_stock_report_html(payload)

    assert "結構指紋" in html
    assert STRUCTURE_FORBIDDEN_RE.search(html) is None
