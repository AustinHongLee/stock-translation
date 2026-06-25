from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.analyze.forecast_lab import build_forecast_lab
from app.models import DailyPrice, StockProfile
from app.store.sqlite_store import SQLiteStore
from app.web.api import build_stock_payload


STATIC_DIR = Path("app/ui/static")
FORBIDDEN_RE = re.compile(
    r"目標價|買進|賣出|買賣點|停損|停利|保證|必漲|必跌|All ?in|梭哈|Target|Buy|Sell|包賺|穩賺",
    re.IGNORECASE,
)


class ForecastLabGuardrailTests(unittest.TestCase):
    def test_forecast_lab_output_keeps_required_guardrails(self) -> None:
        result = build_forecast_lab(_sample_payload())
        body = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["experimental"])
        self.assertIn(result["lean"], {"偏多", "中性", "偏空"})
        self.assertIn("limitations", result)
        self.assertIn("disclaimer", result)
        self.assertIn("缺新聞、法人、風險", result["limitations"])
        self.assertIsNone(FORBIDDEN_RE.search(body))

    def test_experimental_html_copy_has_no_forbidden_action_language(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        snippets = [
            _fragment(html, 'id="forecastLabBtn"', "</button>"),
            _fragment(html, 'id="forecastLabPanel"', "</section>"),
            _fragment(html, 'id="forecastLabOverlay"', "</div>"),
        ]
        body = "\n".join(snippets)

        self.assertIn("技術面推估", body)
        self.assertIn("非投資建議", body)
        self.assertIsNone(FORBIDDEN_RE.search(body))

    def test_default_stock_payload_does_not_embed_forecast_lab(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles([StockProfile("2330", "台積電", "台積電")])
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 10), 100, 105, 99, 102, 10),
                        DailyPrice("2330", date(2026, 6, 11), 102, 108, 101, 107, 12),
                    ]
                )
                payload = build_stock_payload(store, "2330", days=30, quote_provider=None)

        self.assertNotIn("forecast_lab", payload)
        self.assertNotIn("forecastLab", json.dumps(payload, ensure_ascii=False))


def _sample_payload() -> dict[str, object]:
    return {
        "prices": [{"date": "2026-06-20", "close": 112}],
        "features": {
            "latest": {
                "close": 112,
                "ma5": 110,
                "ma20": 105,
                "ma60": 98,
                "macd_histogram": 1.4,
                "kd_k": 62,
                "kd_d": 54,
                "rsi_14": 61,
                "roc_20": 7.2,
            }
        },
        "historical_frequency": {"available": False, "events": []},
        "structure": {"available": False, "dimensions": []},
        "chips": {"available": False},
        "chips_series": [],
        "news": {},
    }


def _fragment(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start) + len(end_marker)
    return source[start:end]


if __name__ == "__main__":
    unittest.main()
