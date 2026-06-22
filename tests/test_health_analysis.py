from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.analyze.health import calculate_health_metrics
from app.models import DailyPrice


class HealthAnalysisTests(unittest.TestCase):
    def test_calculate_health_metrics_from_daily_prices(self) -> None:
        prices = [
            DailyPrice(
                stock_id="2330",
                date=date(2026, 1, 1) + timedelta(days=index),
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100 + index,
                volume=1000,
            )
            for index in range(61)
        ]

        metrics = calculate_health_metrics(prices)

        self.assertEqual(metrics.trend.latest_close, 160)
        self.assertEqual(metrics.trend.close_20d_ago, 140)
        self.assertAlmostEqual(metrics.trend.change_20d_percent, (160 / 140 - 1) * 100)
        self.assertEqual(metrics.price_position.high, 161)
        self.assertEqual(metrics.price_position.low, 99)
        self.assertFalse(metrics.profitability.available)
        self.assertGreater(metrics.volatility.sample_days, 0)

    def test_bad_daily_rows_do_not_pollute_health_metrics(self) -> None:
        prices = [
            DailyPrice("2330", date(2026, 1, 1), 10, 11, 9, 10, 1000),
            DailyPrice("2330", date(2026, 1, 2), 0, 0, 0, 0, 1000),
            DailyPrice("2330", date(2026, 1, 3), 500, 500, 500, 500, 0),
            DailyPrice("2330", date(2026, 1, 4), 10, 12, 10, 11, 1000),
            DailyPrice("2330", date(2026, 1, 5), 11, 13, 11, 12, 1000),
        ]

        metrics = calculate_health_metrics(prices)

        self.assertEqual(metrics.trend.latest_close, 12)
        self.assertEqual(metrics.trend.close_20d_ago, 10)
        self.assertEqual(metrics.price_position.high, 13)
        self.assertEqual(metrics.price_position.low, 9)
        self.assertEqual(metrics.volatility.sample_days, 2)


if __name__ == "__main__":
    unittest.main()
