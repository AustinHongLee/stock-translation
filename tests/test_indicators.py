from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.analyze.indicator_registry import indicator_catalog
from app.analyze.indicators import compute_features


def _rows(closes: list[float], *, start: date = date(2026, 1, 1)) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "date": start + timedelta(days=index),
                "open": close - 0.5,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return rows


class IndicatorEngineTests(unittest.TestCase):
    def test_basic_price_candle_return_sma_and_ema_values(self) -> None:
        bundle = compute_features(_rows([10, 11, 12, 13, 14, 15])).to_json(include_catalog=False)
        series = bundle["series"]  # type: ignore[index]

        self.assertEqual(series["previous_close"][0], None)
        self.assertEqual(series["previous_close"][1], 10)
        self.assertEqual(series["price_change"][1], 1)
        self.assertEqual(series["price_change_percent"][1], 10)
        self.assertEqual(series["typical_price"][-1], 15)
        self.assertEqual(series["weighted_price"][-1], 15)
        self.assertEqual(series["body_size"][-1], 0.5)
        self.assertEqual(series["candle_range"][-1], 2)
        self.assertEqual(series["body_ratio"][-1], 0.25)
        self.assertEqual(series["return_5d"][-1], 50)
        self.assertEqual(series["ma5"][-1], 13)
        self.assertEqual(series["ema5"][4], 12)
        self.assertEqual(series["ema5"][5], 13)
        self.assertEqual(bundle["latest"]["ma5"], 13)  # type: ignore[index]

    def test_visible_slice_keeps_warmup_ma60_on_first_visible_bar(self) -> None:
        rows = _rows([float(i) for i in range(2, 82)])
        visible_dates = [item["date"].isoformat() for item in rows[-10:]]  # type: ignore[union-attr]

        bundle = compute_features(rows, visible_dates=visible_dates).to_json(include_catalog=False)
        series = bundle["series"]  # type: ignore[index]

        self.assertEqual(bundle["dates"][0], visible_dates[0])  # type: ignore[index]
        self.assertEqual(len(bundle["dates"]), 10)  # type: ignore[arg-type]
        self.assertEqual(series["ma60"][0], 42.5)
        self.assertEqual(bundle["warmup"]["warmup_rows"], 70)  # type: ignore[index]

    def test_ma_cross_uses_previous_and_current_bars(self) -> None:
        rows = _rows([100.0] * 60 + [200.0])

        series = compute_features(rows).series

        self.assertTrue(series["golden_cross"][-1])
        self.assertFalse(series["death_cross"][-1])

    def test_advanced_layers_include_volume_breakout_oscillator_and_experimental_payloads(self) -> None:
        rows = _rows([100 + i * 0.5 for i in range(79)] + [155])
        rows[-1]["volume"] = 5000

        bundle = compute_features(rows).to_json(include_catalog=False)
        latest = bundle["latest"]  # type: ignore[index]

        self.assertAlmostEqual(latest["atr_14"], 3.071429)
        self.assertGreater(latest["hv_20"], 0)
        self.assertGreater(latest["volume_ratio"], 3)
        self.assertTrue(latest["volume_spike"])
        self.assertTrue(latest["new_volume_high_20"])
        self.assertGreater(latest["obv"], 0)
        self.assertGreater(latest["volume_trend"], 0)
        self.assertEqual(latest["high_20"], 156)
        self.assertEqual(latest["low_20"], 129)
        self.assertTrue(latest["breakout_20"])
        self.assertGreater(latest["breakout_strength_20"], 10)
        self.assertEqual(latest["rsi_14"], 100)
        self.assertGreater(latest["macd"], latest["macd_signal"])
        self.assertGreater(latest["macd_histogram"], 0)
        self.assertGreater(latest["kd_k"], latest["kd_d"])
        self.assertTrue(latest["bb_breakout"])
        self.assertGreater(latest["bb_position"], 1)
        self.assertEqual(latest["trend_direction"], "多")
        self.assertGreater(latest["trend_strength"], 0)

        score = latest["momentum_score"]
        self.assertEqual(score["confidence"], "experimental")
        self.assertIn("非機率", score["label_note"])
        pattern = latest["double_top"]
        self.assertFalse(pattern["matched"])
        self.assertIn("不是買賣訊號", pattern["disclaimer"])

    def test_catalog_exposes_registry_driven_groups_and_presets(self) -> None:
        catalog = indicator_catalog()
        feature_keys = {item["key"] for item in catalog["features"]}  # type: ignore[index]
        category_keys = [item["key"] for item in catalog["categories"]]  # type: ignore[index]

        self.assertIn("ma20", feature_keys)
        self.assertIn("ema200", feature_keys)
        self.assertIn("ma_state", category_keys)
        self.assertIn("newbie", catalog["presets"])  # type: ignore[operator]
        self.assertIn("ma60", catalog["presets"]["newbie"]["enabled"])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
