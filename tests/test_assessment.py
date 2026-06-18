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


if __name__ == "__main__":
    unittest.main()
