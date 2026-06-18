from __future__ import annotations

import unittest

from app.analyze.vital_signs import build_vital_signs_report
from app.models import FinancialStatement, MonthlyRevenue


class VitalSignsTests(unittest.TestCase):
    def test_loss_stock_surfaces_repair_signals(self) -> None:
        report = build_vital_signs_report(
            monthly_revenues=[
                _revenue("2026-05", -12.5),
                _revenue("2026-04", -8.0),
                _revenue("2026-03", 3.0),
            ],
            financials=[
                _financial(2026, 1, eps=-0.2, revenue=1000, gross_profit=120, net_income=-80),
                _financial(2025, 4, eps=-0.4, revenue=900, gross_profit=100, net_income=-120),
            ],
        )

        self.assertEqual(report.tone, "caution")
        facts = {item.key: item for item in report.facts}
        self.assertEqual(facts["eps"].tone, "caution")
        self.assertIn("連續 2 季虧損", facts["eps"].text)
        self.assertEqual(facts["break_even"].value, "未站上")

    def test_positive_turnaround_keeps_price_out_of_the_answer(self) -> None:
        report = build_vital_signs_report(
            monthly_revenues=[
                _revenue("2026-05", 25.0),
                _revenue("2026-04", 18.0),
                _revenue("2026-03", 12.0),
            ],
            financials=[
                _financial(2026, 1, eps=0.3, revenue=1000, gross_profit=260, net_income=30),
                _financial(2025, 4, eps=-0.1, revenue=900, gross_profit=180, net_income=-10),
            ],
        )

        text = str(report)
        self.assertIn("體質", report.title)
        self.assertNotIn("目標價", text)
        self.assertNotIn("買", text)
        facts = {item.key: item for item in report.facts}
        self.assertEqual(facts["revenue_yoy"].tone, "positive")
        self.assertIn("EPS 轉正", facts["eps"].text)

    def test_negative_gross_margin_is_caution_even_without_previous_quarter(self) -> None:
        report = build_vital_signs_report(
            monthly_revenues=[],
            financials=[
                _financial(2026, 1, eps=0.1, revenue=1000, gross_profit=-100, net_income=10),
            ],
        )

        facts = {item.key: item for item in report.facts}
        self.assertEqual(facts["gross_margin"].tone, "caution")
        self.assertIn("毛利率仍為負", facts["gross_margin"].text)


def _revenue(year_month: str, yoy: float) -> MonthlyRevenue:
    return MonthlyRevenue(
        stock_id="3576",
        year_month=year_month,
        company_name="聯合再生",
        industry="光電業",
        current_month_revenue=1000,
        previous_month_revenue=None,
        last_year_month_revenue=None,
        mom_percent=None,
        yoy_percent=yoy,
        cumulative_revenue=None,
        cumulative_last_year_revenue=None,
        cumulative_yoy_percent=None,
    )


def _financial(
    year: int,
    quarter: int,
    *,
    eps: float,
    revenue: int,
    gross_profit: int,
    net_income: int,
) -> FinancialStatement:
    return FinancialStatement(
        stock_id="3576",
        year=year,
        quarter=quarter,
        company_name="聯合再生",
        revenue=revenue,
        gross_profit=gross_profit,
        operating_income=net_income,
        non_operating_income_expense=0,
        pre_tax_income=net_income,
        net_income=net_income,
        parent_net_income=net_income,
        eps=eps,
        total_assets=10000,
        total_liabilities=4000,
        parent_equity=6000,
        total_equity=6000,
        book_value_per_share=10,
    )


if __name__ == "__main__":
    unittest.main()
