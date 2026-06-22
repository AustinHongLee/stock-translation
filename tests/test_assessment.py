import math
import unittest

from app.analyze.assessment import build_assessment, rsi, kd, sma
from app.news.classifier import contains_forbidden


def _prices(closes):
    out = []
    for i, c in enumerate(closes):
        out.append({"date": f"2026-01-{(i % 28) + 1:02d}", "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10000 + i})
    return out


class AssessmentTest(unittest.TestCase):
    def test_insufficient_data(self):
        a = build_assessment(_prices([10, 11, 12]))
        self.assertFalse(a["available"])

    def test_basic_factors_present(self):
        a = build_assessment(_prices([50 + i * 0.2 for i in range(90)]))
        self.assertTrue(a["available"])
        keys = {f["key"] for f in a["factors"]}
        self.assertEqual({"ma", "bias", "rsi", "kd", "volume", "position"} - keys, set())
        self.assertEqual(a["counts"]["bull"] + a["counts"]["bear"] + a["counts"]["neutral"], len(a["factors"]))

    def test_chips_and_valuation_factors_optional(self):
        a = build_assessment(
            _prices([50 + i * 0.1 for i in range(90)]),
            chips={"available": True, "level": "警戒", "consecutive_total_sell_days": 6, "sum_20": {"total_net": -500000}},
            valuation={"bands": {"pe": {"available": True, "current_percentile": 90}}},
        )
        keys = {f["key"] for f in a["factors"]}
        self.assertIn("chips", keys)
        self.assertIn("valuation", keys)

    def test_rsi_kd_sma_math(self):
        self.assertEqual(sma([1, 2, 3, 4], 2), 3.5)
        self.assertEqual(sma([0, float("nan"), 20, 30], 2), 25)
        self.assertEqual(rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]), 100.0)
        k, d = kd(_prices([10, 11, 12, 13, 14, 15, 16, 17, 18, 19]))
        self.assertTrue(0 <= k <= 100 and 0 <= d <= 100)

    def test_no_forbidden_words(self):
        a = build_assessment(
            _prices([60 - i * 0.3 for i in range(90)]),
            chips={"available": True, "level": "注意", "consecutive_total_sell_days": 3, "sum_20": {"total_net": -100000}},
            valuation={"bands": {"pe": {"available": True, "current_percentile": 15}}},
            revenue_summary={"facts": [{"label": "年增率", "value": -20}]},
        )
        blob = a["summary"] + " " + a["disclaimer"]
        for f in a["factors"]:
            blob += " " + f["reading"] + " " + f["traditional"]
        self.assertEqual(contains_forbidden(blob), [])


    def test_rsi_wilder_reference(self):
        # StockCharts 經典 RSI(14) 範例，標準 Wilder 答案 ≈ 70.46
        sc = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
              46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        self.assertAlmostEqual(rsi(sc), 70.5, delta=0.3)

    def test_kd_standard_values(self):
        bars = [{"high": h, "low": lo, "close": c} for h, lo, c in [
            (8.64, 8.20, 8.25), (8.45, 8.18, 8.41), (8.49, 8.08, 8.14),
            (8.28, 8.05, 8.11), (8.92, 8.10, 8.92), (9.81, 9.81, 9.81),
            (9.20, 8.83, 8.96), (8.90, 8.30, 8.49), (9.05, 8.67, 8.82),
            (9.55, 8.62, 8.74)]]
        k, d = kd(bars, 9)
        self.assertAlmostEqual(k, 45.0, delta=0.2)
        self.assertAlmostEqual(d, 47.9, delta=0.2)

    def test_assessment_fixed_thresholds(self):
        prices = _prices([float(i) for i in range(2, 62)])

        result = build_assessment(prices)
        by_key = {factor["key"]: factor for factor in result["factors"]}

        self.assertEqual(by_key["ma"]["value"], "MA5 59.00 / MA20 51.50 / MA60 31.50")
        self.assertIn("正乖離偏大（+18.4%）", by_key["bias"]["reading"])
        self.assertEqual(by_key["bias"]["lean"], "偏空解讀")
        self.assertEqual(by_key["rsi"]["value"], 100.0)
        self.assertEqual(by_key["position"]["value"], "100%")
        self.assertEqual(by_key["position"]["lean"], "偏空解讀")

    def test_bad_price_rows_do_not_pollute_indicators(self):
        clean = _prices([
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84,
            46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
        ])
        dirty = clean[:5] + [
            {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 1000},
            {"open": math.nan, "high": math.nan, "low": math.nan, "close": math.nan, "volume": 1000},
        ] + clean[5:]

        self.assertAlmostEqual(rsi([p["close"] for p in dirty]), rsi([p["close"] for p in clean]))
        dirty_for_kd = clean[:5] + [{"open": 999, "high": 999, "low": 999, "close": 999, "volume": 0}] + clean[5:]
        self.assertEqual(kd(dirty_for_kd, 9), kd(clean, 9))

        long_clean = _prices([50 + i * 0.2 for i in range(90)])
        long_dirty = long_clean[:30] + [
            {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 1000},
            {"open": 5000, "high": 5000, "low": 5000, "close": 5000, "volume": 0},
        ] + long_clean[30:]
        clean_factors = {f["key"]: f for f in build_assessment(long_clean)["factors"]}
        dirty_factors = {f["key"]: f for f in build_assessment(long_dirty)["factors"]}
        self.assertEqual(dirty_factors["ma"]["value"], clean_factors["ma"]["value"])
        self.assertEqual(dirty_factors["rsi"]["value"], clean_factors["rsi"]["value"])


if __name__ == "__main__":
    unittest.main()
