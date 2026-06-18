import unittest

from app.analyze.levels import compute_support_resistance, swing_pivots


def _p(triples):
    return [{"high": h, "low": lo, "close": c} for h, lo, c in triples]


class LevelsTest(unittest.TestCase):
    def test_insufficient_data(self):
        r = compute_support_resistance(_p([(10, 9, 9.5)] * 4))
        self.assertFalse(r["available"])
        self.assertEqual(r["status"], "資料不足")

    def test_near_support(self):
        # 造一個明顯波段低 8.0，現價 8.1（在支撐上方約 1.25%）→ 接近波撐
        seq = [(11, 10, 10.5), (11, 10, 10.4), (10.5, 9.5, 9.6), (9, 8.0, 8.2),
               (9.5, 9.0, 9.3), (10, 9.5, 9.8), (10.2, 9.8, 10.0), (10.1, 9.9, 8.1)]
        r = compute_support_resistance(seq and _p(seq), k=2, tolerance=2.0)
        self.assertTrue(r["available"])
        self.assertEqual(r["support"], 8.0)
        self.assertEqual(r["status"], "接近波撐")

    def test_pivots_strict(self):
        highs = [1, 2, 5, 2, 1]
        lows = [5, 4, 1, 4, 5]
        ph, pl = swing_pivots(highs, lows, 2)
        self.assertEqual(ph, [5])
        self.assertEqual(pl, [1])


if __name__ == "__main__":
    unittest.main()
