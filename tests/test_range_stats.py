from __future__ import annotations

import math
import statistics
import unittest
from datetime import date

from app.analyze.range_stats import compute_range_stats
from app.models import DailyPrice
from app.news.classifier import contains_forbidden


class RangeStatsTest(unittest.TestCase):
    def test_compute_range_stats_known_series(self) -> None:
        prices = [
            {"date": "2026-06-01", "open": 10, "high": 12, "low": 9, "close": 10, "volume": 1000},
            {"date": "2026-06-02", "open": 10, "high": 13, "low": 10, "close": 12, "volume": 2000},
            {"date": "2026-06-03", "open": 12, "high": 15, "low": 11, "close": 15, "volume": 3000},
            {"date": "2026-06-04", "open": 15, "high": 16, "low": 14, "close": 14, "volume": 4000},
        ]

        stats = compute_range_stats(prices, 0, 3)

        self.assertTrue(stats["available"])
        self.assertEqual(stats["start_date"], "2026-06-01")
        self.assertEqual(stats["end_date"], "2026-06-04")
        self.assertEqual(stats["trading_days"], 4)
        self.assertEqual(stats["start_price"], 10)
        self.assertEqual(stats["end_price"], 14)
        self.assertEqual(stats["price_change"], 4)
        self.assertEqual(stats["price_change_percent"], 40)
        self.assertEqual(stats["highest"], 16)
        self.assertEqual(stats["lowest"], 9)
        self.assertEqual(stats["amplitude_percent"], 70)
        self.assertEqual(stats["average_volume"], 2500)
        self.assertAlmostEqual(stats["vwap"], 13.5)

        returns = [0.2, 0.25, -1 / 15]
        expected_vol = statistics.stdev(returns) * math.sqrt(252) * 100
        self.assertAlmostEqual(stats["annualized_volatility_percent"], expected_vol)
        self.assertEqual(contains_forbidden(str(stats)), [])

    def test_compute_range_stats_swaps_and_clamps_indexes(self) -> None:
        prices = [
            DailyPrice("2330", date(2026, 6, 1), 10, 11, 9, 10, 1000),
            DailyPrice("2330", date(2026, 6, 2), 10, 12, 10, 11, 2000),
            DailyPrice("2330", date(2026, 6, 3), 11, 13, 10, 12, 3000),
        ]

        stats = compute_range_stats(prices, 99, 1)

        self.assertTrue(stats["available"])
        self.assertEqual(stats["start_index"], 1)
        self.assertEqual(stats["end_index"], 2)
        self.assertEqual(stats["start_date"], date(2026, 6, 2))
        self.assertEqual(stats["end_date"], date(2026, 6, 3))

    def test_compute_range_stats_prefers_trade_value_vwap(self) -> None:
        prices = [
            {"date": "2026-06-01", "high": 11, "low": 9, "close": 10, "volume": 100, "trade_value": 1200},
            {"date": "2026-06-02", "high": 13, "low": 10, "close": 12, "volume": 300, "trade_value": 3300},
        ]

        stats = compute_range_stats(prices, 0, 1)

        self.assertAlmostEqual(stats["vwap"], 11.25)

    def test_compute_range_stats_handles_empty(self) -> None:
        stats = compute_range_stats([], 0, 1)

        self.assertFalse(stats["available"])


if __name__ == "__main__":
    unittest.main()
