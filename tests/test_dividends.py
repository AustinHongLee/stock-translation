from __future__ import annotations

import unittest

from app.analyze.dividends import (
    annual_cash_dividends_by_year,
    dedupe_dividend_records,
)
from app.models import DividendRecord


class DividendAggregationTests(unittest.TestCase):
    def test_paid_ex_dividend_does_not_double_count_annual_announcement(self) -> None:
        records = dedupe_dividend_records(
            [
                DividendRecord("2330", 115, "除息 06/11", "除息", None, None, 6.0, 0, source="TWSE_TWT49U"),
                DividendRecord("2330", 115, "年度", "股東會確認", None, None, 6.2, 0, source="TWSE_T187AP45"),
                DividendRecord("2330", 115, "第1季", "董事會決議", None, None, 7.0, 0, source="TWSE_T187AP45"),
            ]
        )

        self.assertEqual({item.period for item in records}, {"除息 06/11", "第1季"})
        self.assertEqual(annual_cash_dividends_by_year(records), {115: 13.0})

    def test_numeric_period_is_treated_as_annual_dividend(self) -> None:
        records = [
            DividendRecord("2303", 115, "114", "股東會確認", None, None, 2.6, 0, source="TWSE_T187AP45")
        ]

        self.assertEqual(annual_cash_dividends_by_year(records), {115: 2.6})

    def test_roc_quarter_periods_form_annual_total(self) -> None:
        records = [
            DividendRecord("2330", 115, f"115Q{quarter}", "董事會決議", None, None, cash, 0)
            for quarter, cash in [(1, 3.0), (2, 3.0), (3, 4.0), (4, 4.0)]
        ]

        self.assertEqual(annual_cash_dividends_by_year(records), {115: 14.0})


if __name__ == "__main__":
    unittest.main()
