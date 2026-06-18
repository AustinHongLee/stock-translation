from __future__ import annotations

import unittest
from datetime import date

from app.analyze.methods import calculate_pe_band, calculate_pb_band, calculate_relative_valuation
from app.analyze.suitability import assess_valuation_suitability
from app.models import DividendRecord, FinancialStatement, MarketValuation, StockProfile


def _financial(
    *,
    year: int = 2026,
    quarter: int = 1,
    eps: float | None = 2.0,
    book_value_per_share: float | None = 20.0,
) -> FinancialStatement:
    return FinancialStatement(
        stock_id="TEST",
        year=year,
        quarter=quarter,
        company_name="測試公司",
        revenue=1000,
        gross_profit=300,
        operating_income=200,
        non_operating_income_expense=0,
        pre_tax_income=200,
        net_income=150,
        parent_net_income=150,
        eps=eps,
        total_assets=3000,
        total_liabilities=1000,
        parent_equity=2000,
        total_equity=2000,
        book_value_per_share=book_value_per_share,
    )


class RelativeValuationMethodsTest(unittest.TestCase):
    def test_pe_band_uses_official_pe_implied_eps_when_ttm_is_missing(self) -> None:
        market = MarketValuation("TEST", date(2026, 6, 12), pe_ratio=20.0, dividend_yield=1.0, pb_ratio=2.0)

        result = calculate_pe_band(
            financials=[_financial(eps=2.0)],
            market=market,
            latest_close=200.0,
            company_type="general",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.basis_source, "official_pe_implied_ttm_eps")  # type: ignore[union-attr]
        self.assertAlmostEqual(result.basis_value, 10.0)  # type: ignore[arg-type]
        self.assertAlmostEqual(result.estimates[0].price, 160.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.estimates[1].price, 200.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.estimates[2].price, 240.0)  # type: ignore[union-attr]
        self.assertEqual(result.estimates[0].label, "倍數 -20%")  # type: ignore[union-attr]
        self.assertEqual(result.estimates[1].label, "目前倍數")  # type: ignore[union-attr]
        self.assertEqual(result.estimates[2].label, "倍數 +20%")  # type: ignore[union-attr]
        self.assertAlmostEqual(result.fair_difference, 0.0)  # type: ignore[arg-type]

    def test_pe_band_prefers_latest_four_quarters_eps(self) -> None:
        financials = [
            _financial(year=2026, quarter=1, eps=2.0),
            _financial(year=2025, quarter=4, eps=3.0),
            _financial(year=2025, quarter=3, eps=4.0),
            _financial(year=2025, quarter=2, eps=5.0),
        ]

        result = calculate_pe_band(
            financials=financials,
            market=None,
            latest_close=200.0,
            company_type="mature_dividend",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.basis_source, "latest_four_quarters_eps")  # type: ignore[union-attr]
        self.assertAlmostEqual(result.basis_value, 14.0)  # type: ignore[arg-type]
        self.assertAlmostEqual(result.estimates[1].price, 200.0)  # type: ignore[union-attr]
        self.assertEqual(result.confidence, "high")  # type: ignore[union-attr]

    def test_pb_band_uses_latest_book_value_per_share(self) -> None:
        market = MarketValuation("TEST", date(2026, 6, 12), pe_ratio=20.0, dividend_yield=1.0, pb_ratio=3.0)

        result = calculate_pb_band(
            financials=[_financial(book_value_per_share=25.0)],
            market=market,
            latest_close=100.0,
            company_type="cyclical",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.basis_source, "latest_financial_book_value")  # type: ignore[union-attr]
        self.assertAlmostEqual(result.current_multiple, 4.0)  # type: ignore[arg-type]
        self.assertAlmostEqual(result.estimates[0].price, 80.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.estimates[1].price, 100.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(result.estimates[2].price, 120.0)  # type: ignore[union-attr]

    def test_relative_valuation_adds_pb_when_suitability_route_says_peer_pe_pb(self) -> None:
        dividends = [
            DividendRecord("TEST", 2025, "年度", "已分派", None, None, 0.1, 0.0),
        ]
        market = MarketValuation("TEST", date(2026, 6, 12), pe_ratio=30.0, dividend_yield=0.2, pb_ratio=2.0)
        suitability = assess_valuation_suitability(
            dividends=dividends,
            financials=[_financial()],
            market=market,
            latest_close=100.0,
            profile=StockProfile("TEST", "測試", "測試"),
            as_of_date=date(2026, 6, 16),
        )

        result = calculate_relative_valuation(
            financials=[_financial()],
            market=market,
            latest_close=100.0,
            suitability=suitability,
        )

        self.assertTrue(any(item.method == "pb_band" for item in result.methods))

    def test_relative_valuation_refuses_newly_listed_no_estimate_stock(self) -> None:
        dividends = [
            DividendRecord("TEST", 2025, "年度", "已分派", None, None, 0.1, 0.0),
        ]
        market = MarketValuation("TEST", date(2026, 6, 12), pe_ratio=30.0, dividend_yield=0.2, pb_ratio=2.0)
        suitability = assess_valuation_suitability(
            dividends=dividends,
            financials=[_financial()],
            market=market,
            latest_close=100.0,
            profile=StockProfile("TEST", "測試", "測試", listed_date=date(2025, 1, 1)),
            as_of_date=date(2026, 6, 16),
        )

        result = calculate_relative_valuation(
            financials=[_financial()],
            market=market,
            latest_close=100.0,
            suitability=suitability,
        )

        self.assertEqual(result.status, "not_applicable")
        self.assertEqual(result.methods, [])
        self.assertIn("上市時間太短", result.notes[0])  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
