from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.explain.rule_based import build_rule_based_health_report
from app.news.classifier import contains_forbidden
from app.analyze.suitability import ValuationSuitability
from app.analyze.valuation import DividendSummary, ValuationResult
from app.models import DailyPrice, FinancialStatement, StockProfile


class RuleBasedExplainTests(unittest.TestCase):
    def test_report_has_six_sections_and_no_recommendation_words(self) -> None:
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
        profile = StockProfile(
            stock_id="2330",
            name="台灣積體電路製造股份有限公司",
            short_name="台積電",
        )

        report = build_rule_based_health_report(profile=profile, prices=prices)
        text = str(report)

        self.assertEqual(len(report["sections"]), 6)  # type: ignore[arg-type]
        self.assertIn("本內容只解讀已同步資料", report["disclaimer"])
        for section in report["sections"]:  # type: ignore[union-attr]
            self.assertEqual(len(section["sentences"]), 4)
        for forbidden in ("建議買進", "建議賣出", "可以買", "可以賣", "該買", "會漲", "會跌"):
            self.assertNotIn(forbidden, text)

    def test_profitability_section_uses_financial_statement(self) -> None:
        statement = FinancialStatement(
            stock_id="2330",
            year=2026,
            quarter=1,
            company_name="台積電",
            revenue=1134103440,
            gross_profit=751295421,
            operating_income=658966142,
            non_operating_income_expense=28833545,
            pre_tax_income=687799687,
            net_income=572801304,
            parent_net_income=572479752,
            eps=22.08,
            total_assets=8660949685,
            total_liabilities=2728560764,
            parent_equity=5890960252,
            total_equity=5932388921,
            book_value_per_share=227.17,
        )

        report = build_rule_based_health_report(
            profile=None,
            prices=[],
            financial_statement=statement,
        )
        profitability = [
            item for item in report["sections"] if item["id"] == "profitability"  # type: ignore[index]
        ][0]

        self.assertEqual(profitability["tone"], "positive")
        self.assertIn("EPS", str(profitability))
        self.assertIn("ROE", str(profitability))

    def test_price_position_does_not_use_buy_signal_tone(self) -> None:
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
            for index in range(40)
        ]
        prices.append(
            DailyPrice(
                stock_id="2330",
                date=date(2026, 2, 15),
                open=91,
                high=92,
                low=90,
                close=90,
                volume=1000,
            )
        )

        report = build_rule_based_health_report(profile=None, prices=prices)
        price_position = [
            item for item in report["sections"] if item["id"] == "price_position"  # type: ignore[index]
        ][0]

        self.assertEqual(price_position["tone"], "neutral")
        self.assertIn("低位", str(price_position))
        self.assertNotIn("該買", str(price_position))

    def test_report_includes_dividend_and_valuation_suitability_sections(self) -> None:
        suitability = ValuationSuitability(
            company_type="growth",
            company_type_label="成長股",
            state="low_confidence",
            reasons=["growth_stock", "low_yield"],
            recommended_primary="pe_band",
            recommended_secondary=["revenue_momentum"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="股利法參考性偏低，建議搭配其他方法",
        )
        valuation = ValuationResult(
            dividend_summary=DividendSummary(
                rows=5,
                average_cash_dividend=3.0,
                latest_cash_dividend=2.5,
                latest_stock_dividend=0.0,
                years=[115, 114, 113, 112, 111],
                estimate_source="annual_dividend_records",
            ),
            estimates=[],
            historical_yield=None,
            market=None,
            confidence="medium",
            suitability_notes=[],
            warning="",
        )

        report = build_rule_based_health_report(
            profile=None,
            prices=[],
            suitability=suitability,
            valuation=valuation,
        )
        section_ids = [item["id"] for item in report["sections"]]  # type: ignore[index]

        self.assertIn("dividend_stability", section_ids)
        self.assertIn("valuation_suitability", section_ids)
        self.assertIn("本益比敏感度", str(report))
        self.assertIn("股利資料信心", str(report))

    def test_reason_specific_guidance_is_in_valuation_section(self) -> None:
        suitability = ValuationSuitability(
            company_type="growth",
            company_type_label="成長股",
            state="low_confidence",
            reasons=["growth_stock", "low_yield"],
            recommended_primary="pe_band",
            recommended_secondary=["revenue_momentum"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="股利法參考性偏低，需搭配其他方法",
        )
        report = build_rule_based_health_report(
            profile=None,
            prices=[],
            suitability=suitability,
        )
        valuation_section = [
            item for item in report["sections"] if item["id"] == "valuation_suitability"  # type: ignore[index]
        ][0]
        text = str(valuation_section)

        self.assertIn("營收動能", text)
        self.assertIn("股利不是主軸", text)
        self.assertEqual(contains_forbidden(text), [])


if __name__ == "__main__":
    unittest.main()
