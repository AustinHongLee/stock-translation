from __future__ import annotations

import unittest

from app.analyze.forecast_lab import build_forecast_lab


class ForecastLabTests(unittest.TestCase):
    def test_bullish_input_returns_positive_lean(self) -> None:
        payload = _payload(
            latest={
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
        )

        result = build_forecast_lab(payload)

        self.assertTrue(result["available"])
        self.assertEqual(result["lean"], "偏多")
        self.assertGreater(result["lean_score"], 25)
        self.assertGreaterEqual(len(result["factors"]), 5)
        self.assertEqual(result["scenario"]["d5"]["mid"], 1.2)
        self.assertAlmostEqual(result["history_bullish_ratio"], 0.57)

    def test_bearish_input_returns_negative_lean(self) -> None:
        payload = _payload(
            latest={
                "close": 88,
                "ma5": 90,
                "ma20": 96,
                "ma60": 102,
                "macd_histogram": -1.4,
                "kd_k": 36,
                "kd_d": 49,
                "rsi_14": 38,
                "roc_20": -5.0,
            }
        )

        result = build_forecast_lab(payload)

        self.assertEqual(result["lean"], "偏空")
        self.assertLess(result["lean_score"], -25)

    def test_mixed_input_returns_neutral(self) -> None:
        payload = _payload(
            latest={
                "close": 101,
                "ma5": 100,
                "ma20": 102,
                "ma60": 99,
                "macd_histogram": 0.5,
                "kd_k": 85,
                "kd_d": 80,
                "rsi_14": 78,
                "roc_20": 0.3,
            }
        )

        result = build_forecast_lab(payload)

        self.assertEqual(result["lean"], "中性")
        self.assertLess(abs(result["lean_score"]), 25)

    def test_missing_news_and_chips_cap_confidence(self) -> None:
        payload = _payload(
            latest={
                "close": 112,
                "ma5": 110,
                "ma20": 105,
                "ma60": 98,
                "macd_histogram": 1.4,
                "kd_k": 62,
                "kd_d": 54,
                "rsi_14": 61,
                "roc_20": 7.2,
            },
            news=False,
            chips=False,
            structure_level="high",
        )

        result = build_forecast_lab(payload)

        self.assertEqual(result["confidence"], "medium")
        self.assertIn("新聞風險", result["missing"])
        self.assertIn("法人", result["missing"])
        self.assertIn("缺新聞、法人、風險", result["limitations"])

    def test_small_historical_sample_omits_median(self) -> None:
        payload = _payload(historical_count=3)

        result = build_forecast_lab(payload)

        self.assertIn("d5", result["scenario"])
        self.assertNotIn("mid", result["scenario"]["d5"])
        self.assertTrue(result["scenario"]["d5"]["sample_low"])


def _payload(
    *,
    latest: dict[str, object] | None = None,
    news: bool = True,
    chips: bool = True,
    structure_level: str = "medium",
    historical_count: int = 12,
) -> dict[str, object]:
    latest = latest or {
        "close": 100,
        "ma5": 101,
        "ma20": 100,
        "ma60": 99,
        "macd_histogram": 0.1,
        "kd_k": 50,
        "kd_d": 51,
        "rsi_14": 50,
        "roc_20": 0,
    }
    return {
        "prices": [{"date": "2026-06-20", "close": latest.get("close", 100)}],
        "features": {"latest": latest},
        "historical_frequency": _historical_frequency(historical_count),
        "structure": _structure(structure_level),
        "news": {"available": True, "items": [{"title": "news"}]} if news else {},
        "chips": {"available": chips},
        "chips_series": [{"date": "2026-06-20", "total_net": 10}] if chips else [],
    }


def _historical_frequency(count: int) -> dict[str, object]:
    return {
        "available": True,
        "events": [
            {
                "key": "ma20_reclaim",
                "label": "收回月線",
                "current_match": True,
                "completed_sample_count": count,
                "windows": [
                    {
                        "days": 5,
                        "available": True,
                        "count": count,
                        "positive_ratio_percent": 57,
                        "p10_return_percent": -4.9,
                        "p25_return_percent": -1.2,
                        "median_return_percent": 1.2,
                        "p75_return_percent": 4.3,
                        "p90_return_percent": 6.2,
                    },
                    {
                        "days": 20,
                        "available": True,
                        "count": count,
                        "positive_ratio_percent": 60,
                        "p10_return_percent": -8.5,
                        "p25_return_percent": -2.4,
                        "median_return_percent": 2.8,
                        "p75_return_percent": 8.3,
                        "p90_return_percent": 12.5,
                    },
                ],
            }
        ],
    }


def _structure(level: str) -> dict[str, object]:
    if level == "high":
        return {
            "available": True,
            "dimensions": [
                {"key": "complexity", "bar_level": 2},
                {"key": "turbulence", "bar_level": 2},
                {"key": "chroma", "bar_level": 3},
                {"key": "memory", "bar_level": 4},
            ],
        }
    return {"available": False, "dimensions": []}


if __name__ == "__main__":
    unittest.main()
