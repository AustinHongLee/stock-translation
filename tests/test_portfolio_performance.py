from __future__ import annotations

import unittest
from datetime import date

from app.models import DailyPrice, DividendRecord
from app.portfolio import (
    PortfolioTransaction,
    PriceSnapshot,
    calculate_portfolio,
    calculate_portfolio_performance,
)


class PortfolioPerformanceTests(unittest.TestCase):
    def test_cash_dividend_is_added_to_total_return(self) -> None:
        transactions = [
            PortfolioTransaction("2330", date(2026, 1, 2), "buy", 1000, 100, fee=20, id=1),
            PortfolioTransaction("2330", date(2026, 6, 20), "sell", 200, 120, fee=10, tax=72, id=2),
        ]
        portfolio = calculate_portfolio(
            transactions,
            {"2330": PriceSnapshot(close=130, date=date(2026, 7, 1))},
        )
        dividends = {
            "2330": [
                DividendRecord(
                    "2330",
                    115,
                    "除息 06/15",
                    "除息",
                    date(2026, 6, 15),
                    None,
                    2.0,
                    0.0,
                    source="TWSE_TWT49U",
                )
            ]
        }

        performance = calculate_portfolio_performance(
            portfolio=portfolio,
            transactions=transactions,
            dividends_by_stock=dividends,
            latest_prices={"2330": PriceSnapshot(close=130, date=date(2026, 7, 1))},
        )

        self.assertEqual(performance.cash_dividend_events[0].shares, 1000)
        self.assertAlmostEqual(performance.total_cash_dividends, 2000)
        self.assertAlmostEqual(
            performance.total_return_amount,
            portfolio.total_unrealized_pnl + portfolio.realized_pnl + 2000,
        )
        self.assertIsNotNone(performance.xirr_percent)

    def test_buying_on_ex_date_does_not_receive_that_dividend(self) -> None:
        transactions = [
            PortfolioTransaction("2330", date(2026, 6, 15), "buy", 1000, 100, id=1),
        ]
        portfolio = calculate_portfolio(
            transactions,
            {"2330": PriceSnapshot(close=100, date=date(2026, 7, 1))},
        )
        performance = calculate_portfolio_performance(
            portfolio=portfolio,
            transactions=transactions,
            dividends_by_stock={
                "2330": [
                    DividendRecord(
                        "2330",
                        115,
                        "除息 06/15",
                        "除息",
                        date(2026, 6, 15),
                        None,
                        2.0,
                        0.0,
                        source="TWSE_TWT49U",
                    )
                ]
            },
            latest_prices={"2330": PriceSnapshot(close=100, date=date(2026, 7, 1))},
        )

        self.assertEqual(performance.total_cash_dividends, 0)
        self.assertEqual(performance.cash_dividend_events, [])

    def test_missing_actual_dividend_records_is_flagged(self) -> None:
        transactions = [PortfolioTransaction("2330", date(2026, 1, 2), "buy", 1000, 100)]
        portfolio = calculate_portfolio(
            transactions,
            {"2330": PriceSnapshot(close=100, date=date(2026, 7, 1))},
        )

        performance = calculate_portfolio_performance(
            portfolio=portfolio,
            transactions=transactions,
            dividends_by_stock={"2330": []},
            latest_prices={"2330": PriceSnapshot(close=100, date=date(2026, 7, 1))},
        )

        self.assertFalse(performance.dividend_data_complete)
        self.assertIn("可能偏低", " ".join(performance.notes))

    def test_benchmark_uses_same_cashflow_timing(self) -> None:
        transactions = [
            PortfolioTransaction("2330", date(2026, 1, 2), "buy", 1000, 100, fee=0, id=1),
            PortfolioTransaction("2330", date(2026, 6, 1), "sell", 200, 110, fee=0, tax=0, id=2),
        ]
        portfolio = calculate_portfolio(
            transactions,
            {"2330": PriceSnapshot(close=120, date=date(2026, 7, 1))},
        )

        performance = calculate_portfolio_performance(
            portfolio=portfolio,
            transactions=transactions,
            dividends_by_stock={"2330": []},
            latest_prices={"2330": PriceSnapshot(close=120, date=date(2026, 7, 1))},
            benchmark_prices=[
                DailyPrice("0050", date(2026, 1, 2), 100, 100, 100, 100, 1),
                DailyPrice("0050", date(2026, 6, 1), 120, 120, 120, 120, 1),
                DailyPrice("0050", date(2026, 7, 1), 130, 130, 130, 130, 1),
            ],
        )

        self.assertIsNotNone(performance.benchmark)
        self.assertEqual(performance.benchmark.status, "available")  # type: ignore[union-attr]
        self.assertGreater(performance.benchmark.total_return_amount, 0)  # type: ignore[union-attr]
        self.assertIsNotNone(performance.benchmark.xirr_percent)  # type: ignore[union-attr]

    def test_xirr_returns_none_without_positive_and_negative_flows(self) -> None:
        performance = calculate_portfolio_performance(
            portfolio=calculate_portfolio([]),
            transactions=[],
            dividends_by_stock={},
            latest_prices={},
        )

        self.assertIsNone(performance.xirr_percent)


if __name__ == "__main__":
    unittest.main()

