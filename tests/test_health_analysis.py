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


if __name__ == "__main__":
    unittest.main()

