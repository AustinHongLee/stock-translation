from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.explain.validation import build_validation_brief
from app.models import DailyPrice


class ValidationBriefTests(unittest.TestCase):
    def test_validation_brief_has_three_items_without_buy_sell_instruction(self) -> None:
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

        brief = build_validation_brief(prices)
        text = str(brief)

        self.assertEqual(len(brief["items"]), 3)  # type: ignore[arg-type]
        self.assertIn("明牌驗證", brief["title"])
        self.assertNotIn("建議買進", text)
        self.assertNotIn("建議賣出", text)


if __name__ == "__main__":
    unittest.main()

