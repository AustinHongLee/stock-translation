from __future__ import annotations

import unittest
from datetime import date

from app.analyze.valuation import calculate_dividend_valuation
from app.models import DailyPrice, DividendRecord, MarketValuation


class ValuationAnalysisTests(unittest.TestCase):
    def test_calculate_dividend_valuation_uses_average_cash_dividend(self) -> None:
        dividends = [
            DividendRecord(
                stock_id="2330",
                year=115,
                period="第1季",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=7.0,
                stock_dividend=0.0,
            ),
            DividendRecord(
                stock_id="2330",
                year=114,
                period="第4季",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=6.0,
                stock_dividend=0.0,
            ),
        ]
        market = MarketValuation(
            stock_id="2330",
            date=date(2026, 6, 11),
            pe_ratio=30.25,
            dividend_yield=0.98,
            pb_ratio=9.9,
        )

        result = calculate_dividend_valuation(dividends, market, latest_close=1000)

        self.assertAlmostEqual(result.dividend_summary.average_cash_dividend, 9.8)
        self.assertEqual(result.dividend_summary.estimate_source, "market_yield_implied")
        self.assertEqual(result.estimates[1].scenario, "average_yield")
        self.assertAlmostEqual(result.estimates[1].price, 196.0)
        self.assertIn("不代表交易基準價格", result.warning)

    def test_historical_yield_valuation_uses_five_year_yield_band(self) -> None:
        dividends = [
            DividendRecord(
                stock_id="2542",
                year=114,
                period="年度",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=4.0,
                stock_dividend=0.0,
            ),
            DividendRecord(
                stock_id="2542",
                year=113,
                period="年度",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=5.0,
                stock_dividend=0.0,
            ),
        ]
        prices = [
            DailyPrice("2542", date(2025, 1, 2), 100, 100, 100, 100, 1000),
            DailyPrice("2542", date(2025, 1, 3), 100, 100, 100, 100, 1000),
            DailyPrice("2542", date(2024, 1, 2), 80, 80, 80, 80, 1000),
            DailyPrice("2542", date(2024, 1, 3), 80, 80, 80, 80, 1000),
        ]

        result = calculate_dividend_valuation(
            dividends,
            market=None,
            latest_close=92,
            prices=prices,
            historical_years=5,
        )

        historical = result.historical_yield
        self.assertIsNotNone(historical)
        self.assertEqual(len(historical.years), 2)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.high_yield_percent, 6.25)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.average_yield_percent, 5.125)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.low_yield_percent, 4.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.estimates[0].price, 72.0)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.estimates[1].price, 87.804878, places=5)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.estimates[2].price, 112.5)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.cheap_difference, 20.0)  # type: ignore[union-attr]

    def test_historical_yield_valuation_falls_back_to_market_implied_dividend(self) -> None:
        dividends = [
            DividendRecord(
                stock_id="2330",
                year=115,
                period="第1季",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=7.0,
                stock_dividend=0.0,
            ),
            DividendRecord(
                stock_id="2330",
                year=114,
                period="第4季",
                status="董事會決議",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=6.0,
                stock_dividend=0.0,
            ),
        ]
        prices = [
            DailyPrice("2330", date(2026, 1, 2), 2250, 2250, 2250, 2250, 1000),
            DailyPrice("2330", date(2026, 1, 3), 2250, 2250, 2250, 2250, 1000),
            DailyPrice("2330", date(2025, 1, 2), 1500, 1500, 1500, 1500, 1000),
            DailyPrice("2330", date(2025, 1, 3), 1500, 1500, 1500, 1500, 1000),
        ]
        market = MarketValuation(
            stock_id="2330",
            date=date(2026, 6, 11),
            pe_ratio=30.25,
            dividend_yield=0.98,
            pb_ratio=9.9,
        )

        result = calculate_dividend_valuation(
            dividends,
            market=market,
            latest_close=2250,
            prices=prices,
            historical_years=5,
        )

        historical = result.historical_yield
        self.assertIsNotNone(historical)
        self.assertEqual(len(historical.years), 2)  # type: ignore[union-attr]
        self.assertIn("估計年股利", historical.price_basis)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.years[0].cash_dividend, 22.05)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.high_yield_percent, 1.47)  # type: ignore[union-attr]
        self.assertAlmostEqual(historical.low_yield_percent, 0.98)  # type: ignore[union-attr]

    def test_dividend_valuation_averages_latest_five_distribution_years(self) -> None:
        dividends = [
            DividendRecord(
                stock_id="2303",
                year=year,
                period="年度",
                status="除息資料",
                board_date=None,
                shareholder_meeting_date=None,
                cash_dividend=cash,
                stock_dividend=0.0,
            )
            for year, cash in [
                (115, 2.6),
                (114, 2.850164),
                (113, 3.000117),
                (112, 3.600463),
                (111, 3.0),
                (110, 1.599888),
            ]
        ]

        result = calculate_dividend_valuation(
            dividends,
            market=None,
            latest_close=141.5,
            historical_years=5,
        )

        self.assertAlmostEqual(result.dividend_summary.average_cash_dividend, 3.0101488)
        self.assertAlmostEqual(result.estimates[0].price, 48.1623808)
        self.assertAlmostEqual(result.estimates[1].price, 60.202976)
        self.assertAlmostEqual(result.estimates[2].price, 96.3247616)

    def test_dividend_valuation_sums_ex_dividend_events_and_unpaid_announcements(self) -> None:
        dividends = [
            DividendRecord("2330", 115, "除息 03/17", "除息", None, None, 6.0, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 115, "除息 06/11", "除息", None, None, 6.0, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 115, "第1季", "董事會決議", None, None, 7.0, 0.0),
            DividendRecord("2330", 114, "除息 03/18", "除息", None, None, 4.5, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 114, "除息 06/12", "除息", None, None, 4.5, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 114, "除息 09/16", "除息", None, None, 5.0, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 114, "除息 12/11", "除息", None, None, 5.0, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 113, "年度", "除息", None, None, 15.0, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 112, "年度", "除息", None, None, 11.5, 0.0, source="TWSE_TWT49U"),
            DividendRecord("2330", 111, "年度", "除息", None, None, 11.0, 0.0, source="TWSE_TWT49U"),
        ]

        result = calculate_dividend_valuation(
            dividends,
            market=None,
            latest_close=2375,
            historical_years=5,
        )

        self.assertAlmostEqual(result.dividend_summary.average_cash_dividend, 15.1)
        self.assertAlmostEqual(result.estimates[0].price, 241.6)
        self.assertAlmostEqual(result.estimates[1].price, 302.0)
        self.assertAlmostEqual(result.estimates[2].price, 483.2)

    def test_dividend_valuation_marks_short_low_yield_history_as_low_confidence(self) -> None:
        dividends = [
            DividendRecord("7722", 115, "除息 06/15", "除息", None, None, 1.5, 0.0, source="TWSE_TWT49U"),
            DividendRecord("7722", 114, "除息 09/04", "除息", None, None, 1.5, 0.0, source="TWSE_TWT49U"),
        ]
        market = MarketValuation(
            stock_id="7722",
            date=date(2026, 6, 12),
            pe_ratio=47.3,
            dividend_yield=0.6,
            pb_ratio=2.09,
        )
        prices = [
            DailyPrice("7722", date(2026, 6, 15), 327, 337.5, 321, 327, 10),
        ]

        result = calculate_dividend_valuation(
            dividends,
            market=market,
            latest_close=327,
            prices=prices,
            listed_date=date(2024, 12, 5),
        )

        self.assertEqual(result.confidence, "low")
        self.assertTrue(any("未滿 3 年" in note for note in result.suitability_notes))
        self.assertTrue(any("殖利率低於 1%" in note for note in result.suitability_notes))


if __name__ == "__main__":
    unittest.main()
