"""估價適用性規則引擎的契約測試(固定輸入→固定輸出)。"""

from __future__ import annotations

import unittest
from datetime import date

from app.analyze.suitability import assess_valuation_suitability
from app.models import DividendRecord, FinancialStatement, MarketValuation, StockProfile


def _div(year: int, cash: float, stock_id: str = "TEST") -> DividendRecord:
    # 用 TWSE_TWT49U(除息實付)來源,使年度現金股利彙整為當年合計。
    return DividendRecord(
        stock_id=stock_id,
        year=year,
        period="現金",
        status="已分派",
        board_date=None,
        shareholder_meeting_date=None,
        cash_dividend=cash,
        stock_dividend=0.0,
        source="TWSE_TWT49U",
    )


def _fin(year: int, eps: float, *, nonop: float = 0.0, pretax: float = 100.0,
         stock_id: str = "TEST") -> FinancialStatement:
    return FinancialStatement(
        stock_id=stock_id,
        year=year,
        quarter=4,
        company_name="測試公司",
        revenue=1000,
        gross_profit=300,
        operating_income=200,
        non_operating_income_expense=nonop,
        pre_tax_income=pretax,
        net_income=int(eps * 100),
        parent_net_income=int(eps * 100),
        eps=eps,
        total_assets=5000,
        total_liabilities=2000,
        parent_equity=3000,
        total_equity=3000,
        book_value_per_share=30.0,
    )


def _profile(stock_id: str = "TEST", *, listed_date=date(2005, 1, 1),
             industry_code=None, market="TWSE") -> StockProfile:
    return StockProfile(
        stock_id=stock_id,
        name="測試公司",
        short_name="測試",
        industry_code=industry_code,
        market=market,
        listed_date=listed_date,
    )


AS_OF = date(2026, 6, 15)


class ValuationSuitabilityTest(unittest.TestCase):
    def test_mature_high_yield_is_applicable(self):
        dividends = [_div(y, 4.5) for y in (2021, 2022, 2023, 2024, 2025)]
        financials = [_fin(y, 6.0) for y in (2021, 2022, 2023, 2024, 2025)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=110.0, profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "applicable")
        self.assertEqual(result.company_type, "mature_dividend")
        self.assertEqual(result.recommended_primary, "yield")
        self.assertEqual(result.data_confidence, "high")
        self.assertEqual(result.reasons, [])

    def test_low_yield_loss_like_3576_is_not_applicable(self):
        # 3576 情境:平均股利 0.1、現價 21 → 殖利率 <1%;近年曾虧損。
        dividends = [_div(y, 0.1) for y in (2024, 2025)]
        financials = [
            _fin(2023, -1.2), _fin(2024, -0.3), _fin(2025, 0.4),
        ]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=21.0, profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "not_applicable")
        self.assertIn("yield_too_low", result.reasons)
        self.assertIn("loss_history", result.reasons)
        self.assertIn("yield", result.recommended_avoid)
        self.assertNotEqual(result.recommended_primary, "yield")
        self.assertEqual(result.data_confidence, "low")

    def test_newly_listed_insufficient_like_7722_is_not_applicable(self):
        # 7722 情境:只有 2 年股利、上市未滿 3 年、殖利率 <1%。
        dividends = [_div(y, 0.5) for y in (2024, 2025)]
        financials = [_fin(2024, 1.0), _fin(2025, 1.2)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=300.0,  # 0.5/300 ≈ 0.17%
            profile=_profile(listed_date=date(2024, 3, 1)), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "not_applicable")
        self.assertIn("insufficient_data", result.reasons)
        self.assertIn("newly_listed", result.reasons)
        self.assertEqual(result.company_type, "no_estimate")
        self.assertEqual(result.recommended_primary, "none")
        self.assertEqual(result.data_confidence, "low")

    def test_old_construction_stock_with_short_dividend_data_routes_to_pb(self):
        dividends = [_div(y, 2.0) for y in (2024, 2025)]
        financials = [_fin(2025, 4.0)]

        result = assess_valuation_suitability(
            dividends=dividends,
            financials=financials,
            latest_close=80.0,
            profile=_profile(listed_date=date(1999, 5, 3), industry_code="14"),
            as_of_date=AS_OF,
        )

        self.assertEqual(result.state, "not_applicable")
        self.assertIn("insufficient_data", result.reasons)
        self.assertEqual(result.company_type, "construction")
        self.assertEqual(result.recommended_primary, "pb_band")

    def test_cyclical_low_yield_short_data_refuses_valuation(self):
        dividends = [_div(y, 0.1) for y in (2024, 2025)]
        financials = [_fin(2025, 1.0)]

        result = assess_valuation_suitability(
            dividends=dividends,
            financials=financials,
            latest_close=30.0,
            profile=_profile(listed_date=date(2009, 1, 12), industry_code="26"),
            as_of_date=AS_OF,
        )

        self.assertEqual(result.state, "not_applicable")
        self.assertEqual(result.company_type, "no_estimate")
        self.assertEqual(result.recommended_primary, "none")
        self.assertIn("pb_band", result.recommended_avoid)

    def test_etf_is_not_applicable(self):
        dividends = [_div(y, 1.5, stock_id="0056") for y in (2021, 2022, 2023, 2024, 2025)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=[],
            latest_close=35.0,
            profile=_profile(stock_id="0056"), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "not_applicable")
        self.assertEqual(result.company_type, "etf")
        self.assertIn("etf", result.reasons)
        self.assertIn("yield", result.recommended_avoid)

    def test_short_history_is_low_confidence(self):
        # 3-4 年資料、殖利率 4%、獲利穩定為正 → 低信心(short_history)。
        dividends = [_div(y, 4.0) for y in (2023, 2024, 2025)]
        financials = [_fin(y, 5.0) for y in (2023, 2024, 2025)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=100.0, profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "low_confidence")
        self.assertIn("short_history", result.reasons)

    def test_growth_stock_is_low_confidence_and_avoids_yield(self):
        dividends = [_div(y, 0.6) for y in (2021, 2022, 2023, 2024, 2025)]
        financials = [
            _fin(2021, 2.0), _fin(2022, 2.4), _fin(2023, 2.9),
            _fin(2024, 3.5), _fin(2025, 4.2),
        ]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=40.0,  # 0.6/40 = 1.5% → 不觸硬門檻、但偏低
            profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "low_confidence")
        self.assertEqual(result.company_type, "growth")
        self.assertEqual(result.recommended_primary, "pe_band")
        self.assertIn("yield", result.recommended_avoid)

    def test_cyclical_high_earnings_volatility_is_low_confidence(self):
        dividends = [_div(y, 2.5) for y in (2021, 2022, 2023, 2024, 2025)]
        financials = [
            _fin(2021, 1.0), _fin(2022, 5.0), _fin(2023, 2.0),
            _fin(2024, 8.0), _fin(2025, 3.0),
        ]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=100.0,  # 2.5/100 = 2.5% → 不觸低殖利率軟門檻
            profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "low_confidence")
        self.assertEqual(result.company_type, "cyclical")
        self.assertEqual(result.recommended_primary, "pb_band")
        self.assertIn("cyclical", result.reasons)

    def test_yield_boundary_just_below_one_percent(self):
        dividends = [_div(y, 0.99) for y in (2021, 2022, 2023, 2024, 2025)]
        financials = [_fin(y, 5.0) for y in (2021, 2022, 2023, 2024, 2025)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=100.0,  # 0.99%
            profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "not_applicable")
        self.assertIn("yield_too_low", result.reasons)
        self.assertEqual(result.data_confidence, "high")
        self.assertIn("yield", result.recommended_avoid)
        self.assertNotIn("yield", result.recommended_secondary)

    def test_yield_boundary_just_above_one_percent_is_not_hard_excluded(self):
        dividends = [_div(y, 1.2) for y in (2021, 2022, 2023, 2024, 2025)]
        financials = [_fin(y, 5.0) for y in (2021, 2022, 2023, 2024, 2025)]
        result = assess_valuation_suitability(
            dividends=dividends, financials=financials,
            latest_close=100.0,  # 1.2% → 高於硬門檻、低於軟門檻
            profile=_profile(), as_of_date=AS_OF,
        )
        self.assertEqual(result.state, "low_confidence")
        self.assertIn("low_yield", result.reasons)
        self.assertNotIn("yield_too_low", result.reasons)


if __name__ == "__main__":
    unittest.main()
