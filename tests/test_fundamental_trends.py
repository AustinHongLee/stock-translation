from __future__ import annotations

import unittest
from datetime import date

from app.analyze.fundamental_trends import build_fundamental_trends
from app.models import FinancialStatement


class FundamentalTrendsTests(unittest.TestCase):
    def test_builds_chronological_margin_and_roe_series(self) -> None:
        payload = build_fundamental_trends(
            [
                _statement(2026, 1, revenue=2000, gross=1200, op=900, net=700, equity=7000),
                _statement(2025, 4, revenue=1800, gross=900, op=630, net=540, equity=6000),
                _statement(2025, 3, revenue=1600, gross=720, op=480, net=320, equity=5800),
            ]
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["sample_quarters"], 3)
        self.assertEqual([p["quarter_label"] for p in payload["points"]], ["2025Q3", "2025Q4", "2026Q1"])
        gross = _series(payload, "gross_margin_percent")
        roe = _series(payload, "roe_percent")
        self.assertEqual(gross["label"], "毛利率")
        self.assertEqual([p["value"] for p in gross["points"]], [45.0, 50.0, 60.0])
        self.assertEqual(gross["latest"], 60.0)
        self.assertEqual(gross["change"], 10.0)
        self.assertAlmostEqual(roe["latest"], 10.0)
        self.assertIn("不預測未來", payload["disclaimer"])

    def test_zero_revenue_rows_do_not_pollute_margin_series(self) -> None:
        payload = build_fundamental_trends(
            [
                _statement(2025, 4, revenue=0, gross=100, op=50, net=25, equity=1000),
                _statement(2026, 1, revenue=1000, gross=300, op=200, net=100, equity=1000),
            ]
        )

        gross = _series(payload, "gross_margin_percent")
        net = _series(payload, "net_margin_percent")
        roe = _series(payload, "roe_percent")
        self.assertFalse(gross["available"])
        self.assertEqual(gross["valid_points"], 1)
        self.assertIsNone(gross["points"][0]["value"])
        self.assertEqual(net["latest"], 10.0)
        self.assertTrue(roe["available"])
        self.assertEqual(roe["change"], 7.5)

    def test_accepts_json_records_from_existing_payload_shape(self) -> None:
        payload = build_fundamental_trends(
            [
                {
                    "year": 2026,
                    "quarter": 1,
                    "quarter_label": "2026Q1",
                    "gross_margin_percent": 51.2,
                    "operating_margin_percent": 40.0,
                    "net_margin_percent": 30.0,
                    "roe_percent": 8.5,
                    "source_updated_at": "2026-06-22",
                },
                {
                    "year": 2025,
                    "quarter": 4,
                    "quarter_label": "2025Q4",
                    "gross_margin_percent": 49.0,
                    "operating_margin_percent": 39.0,
                    "net_margin_percent": 29.0,
                    "roe_percent": 8.0,
                    "source_updated_at": "2026-03-31",
                },
            ]
        )

        self.assertEqual(payload["source_updated_at"], "2026-06-22")
        self.assertEqual(_series(payload, "operating_margin_percent")["change"], 1.0)


def _statement(
    year: int,
    quarter: int,
    *,
    revenue: int,
    gross: int,
    op: int,
    net: int,
    equity: int,
) -> FinancialStatement:
    return FinancialStatement(
        stock_id="2330",
        year=year,
        quarter=quarter,
        company_name="測試公司",
        revenue=revenue,
        gross_profit=gross,
        operating_income=op,
        non_operating_income_expense=0,
        pre_tax_income=net,
        net_income=net,
        parent_net_income=net,
        eps=1.0,
        total_assets=equity * 2,
        total_liabilities=equity,
        parent_equity=equity,
        total_equity=equity,
        book_value_per_share=10.0,
        source_updated_at=date(year, min(quarter * 3, 12), 28),
    )


def _series(payload: dict[str, object], key: str) -> dict[str, object]:
    return next(item for item in payload["series"] if item["key"] == key)  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
