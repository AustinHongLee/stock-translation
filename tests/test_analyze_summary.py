from __future__ import annotations

import unittest
from datetime import date

from app.analyze.summary import calculate_price_summary
from app.models import DailyPrice


class PriceSummaryTests(unittest.TestCase):
    def test_calculate_price_summary_uses_sorted_prices(self) -> None:
        prices = [
            DailyPrice(
                stock_id="2330",
                date=date(2026, 6, 11),
                open=100,
                high=110,
                low=95,
                close=108,
                volume=10,
            ),
            DailyPrice(
                stock_id="2330",
                date=date(2026, 6, 10),
                open=90,
                high=100,
                low=80,
                close=90,
                volume=10,
            ),
        ]

        summary = calculate_price_summary(prices)

        self.assertEqual(summary.rows, 2)
        self.assertEqual(summary.start_date, "2026-06-10")
        self.assertEqual(summary.end_date, "2026-06-11")
        self.assertEqual(summary.latest_close, 108)
        self.assertEqual(summary.change, 18)
        self.assertEqual(summary.change_percent, 20)
        self.assertAlmostEqual(summary.price_position, (108 - 80) / (110 - 80))

    def test_calculate_price_summary_uses_twse_change_on_ex_dividend_day(self) -> None:
        prices = [
            DailyPrice(
                stock_id="7722",
                date=date(2026, 6, 12),
                open=386,
                high=390,
                low=333.5,
                close=333.5,
                volume=10,
                change=-37,
            ),
            DailyPrice(
                stock_id="7722",
                date=date(2026, 6, 15),
                open=329,
                high=337.5,
                low=321,
                close=327,
                volume=10,
                change=0,
                note="change_marker=X",
            ),
        ]

        summary = calculate_price_summary(prices)

        self.assertEqual(summary.previous_close, 333.5)
        self.assertEqual(summary.change, 0)
        self.assertEqual(summary.change_source, "twse_change")
        self.assertIn("X 標記", summary.change_note or "")


if __name__ == "__main__":
    unittest.main()
