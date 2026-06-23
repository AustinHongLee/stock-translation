import unittest

from app.analyze.levels import compute_support_resistance, swing_pivots


def _p(triples):
    return [{"high": h, "low": lo, "close": c} for h, lo, c in triples]


def _ohlc(rows):
    return [{"open": o, "high": h, "low": lo, "close": c, "volume": v} for o, h, lo, c, v in rows]


class LevelsTest(unittest.TestCase):
    def test_insufficient_data(self):
        r = compute_support_resistance(_p([(10, 9, 9.5)] * 4))
        self.assertFalse(r["available"])
        self.assertEqual(r["status"], "資料不足")

    def test_near_support(self):
        # 造一個明顯波段低 8.0，現價 8.1（在支撐上方約 1.25%）→ 接近波撐
        seq = [(11, 10, 10.5), (11, 10, 10.4), (10.5, 9.5, 9.6), (9, 8.0, 8.2),
               (9.5, 9.0, 9.3), (10, 9.5, 9.8), (10.2, 9.8, 10.0), (10.1, 8.05, 8.1)]
        r = compute_support_resistance(seq and _p(seq), k=2, tolerance=2.0)
        self.assertTrue(r["available"])
        self.assertEqual(r["support"], 8.0)
        self.assertEqual(r["status"], "接近波撐")

    def test_near_resistance_and_middle_status(self):
        seq = [
            (10, 9, 9.5), (11, 10, 10.5), (12, 11, 11.5), (11, 10, 10.8),
            (10.5, 9.8, 10.0), (10.8, 10.0, 10.5), (11.9, 10.8, 11.8),
        ]

        near = compute_support_resistance(_p(seq), k=2, tolerance=2.0)
        middle = compute_support_resistance(_p(seq[:-1] + [(11.0, 10.0, 10.5)]), k=2, tolerance=2.0)

        self.assertEqual(near["resistance"], 12.0)
        self.assertEqual(near["status"], "接近波壓")
        self.assertEqual(middle["status"], "區間中")

    def test_isolated_limit_lock_does_not_become_resistance(self):
        seq = _ohlc([
            (10.0, 10.5, 9.5, 10.0, 1000),
            (10.2, 11.0, 10.0, 10.5, 1000),
            (11.5, 12.0, 10.8, 11.0, 1000),
            (20.0, 20.0, 20.0, 20.0, 1000),  # isolated limit-lock style spike
            (10.8, 11.1, 10.2, 10.8, 1000),
            (10.5, 10.9, 10.0, 10.4, 1000),
            (11.2, 11.8, 10.9, 11.7, 1000),
        ])

        result = compute_support_resistance(seq, k=2, tolerance=3.0)

        self.assertEqual(result["resistance"], 12.0)
        self.assertNotEqual(result["resistance"], 20.0)
        self.assertEqual(result["status"], "接近波壓")

    def test_breakout_does_not_use_lower_pivot_as_resistance(self):
        seq = _p([
            (100, 98, 99),
            (102, 99, 101),
            (105, 100, 104),
            (103, 99, 100),
            (101, 97, 99),
            (104, 98, 103),
            (106, 99, 105),
            (104, 98, 102),
            (103, 97, 100),
            (110, 108, 110),
        ])

        result = compute_support_resistance(seq, k=2)

        self.assertEqual(result["status"], "創區間新高")
        self.assertIsNone(result["resistance"])
        self.assertIsNone(result["dist_resistance_pct"])
        self.assertIsNotNone(result["support"])

    def test_breakdown_does_not_use_higher_pivot_as_support(self):
        seq = _p([
            (102, 99, 101),
            (101, 98, 100),
            (100, 94, 95),
            (101, 97, 100),
            (103, 98, 102),
            (102, 96, 97),
            (101, 93, 94),
            (102, 96, 101),
            (103, 98, 102),
            (92, 90, 90),
        ])

        result = compute_support_resistance(seq, k=2)

        self.assertEqual(result["status"], "創區間新低")
        self.assertIsNone(result["support"])
        self.assertIsNone(result["dist_support_pct"])
        self.assertIsNotNone(result["resistance"])

    def test_bad_rows_keep_high_low_pairs_aligned(self):
        seq = _p([
            (11, 10, 10.5), (11, 10, 10.4), (10.5, 9.5, 9.6), (9, 8.0, 8.2),
            (9.5, 9.0, 9.3), (10, 9.5, 9.8), (10.2, 9.8, 10.0), (10.1, 8.05, 8.1),
        ])
        dirty = seq[:3] + [
            {"high": 99, "low": None, "close": 10},
            {"high": 0, "low": 0, "close": 0},
        ] + seq[3:]

        self.assertEqual(compute_support_resistance(dirty, k=2, tolerance=2.0)["support"], 8.0)

    def test_pivots_strict(self):
        highs = [1, 2, 5, 2, 1]
        lows = [5, 4, 1, 4, 5]
        ph, pl = swing_pivots(highs, lows, 2)
        self.assertEqual(ph, [5])
        self.assertEqual(pl, [1])


if __name__ == "__main__":
    unittest.main()
