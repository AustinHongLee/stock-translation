from __future__ import annotations

import unittest
from datetime import date

from app.portfolio import (
    PortfolioCalculationError,
    PortfolioTransaction,
    PriceSnapshot,
    calculate_portfolio,
)


class PortfolioCalculatorTests(unittest.TestCase):
    def test_multiple_buys_use_moving_average_cost(self) -> None:
        result = calculate_portfolio(
            [
                PortfolioTransaction(
                    stock_id="2330",
                    trade_date=date(2026, 1, 2),
                    side="buy",
                    shares=1000,
                    price=900,
                    fee=100,
                    id=1,
                ),
                PortfolioTransaction(
                    stock_id="2330",
                    trade_date=date(2026, 2, 3),
                    side="buy",
                    shares=1000,
                    price=1000,
                    fee=120,
                    id=2,
                ),
            ],
            {"2330": PriceSnapshot(close=1058, date=date(2026, 6, 12))},
        )

        self.assertEqual(len(result.positions), 1)
        position = result.positions[0]
        self.assertEqual(position.shares, 2000)
        self.assertAlmostEqual(position.cost_basis, 1900220)
        self.assertAlmostEqual(position.average_cost, 950.11)
        self.assertAlmostEqual(position.market_value, 2116000)
        self.assertAlmostEqual(position.unrealized_pnl, 215780)
        self.assertAlmostEqual(position.unrealized_return_percent, 11.3555)
        self.assertEqual(result.realized_pnl, 0)

    def test_sell_uses_average_cost_and_records_realized_pnl(self) -> None:
        result = calculate_portfolio(
            [
                PortfolioTransaction("2330", date(2026, 1, 2), "buy", 1000, 900, fee=100, id=1),
                PortfolioTransaction("2330", date(2026, 2, 3), "buy", 1000, 1000, fee=120, id=2),
                PortfolioTransaction("2330", date(2026, 3, 4), "sell", 500, 1100, fee=80, tax=1650, id=3),
            ],
            {"2330": PriceSnapshot(close=1058, date=date(2026, 6, 12))},
        )

        position = result.positions[0]
        self.assertEqual(position.shares, 1500)
        self.assertAlmostEqual(position.cost_basis, 1425165)
        self.assertAlmostEqual(position.average_cost, 950.11)
        self.assertAlmostEqual(result.realized_pnl, 73215)
        self.assertAlmostEqual(position.market_value, 1587000)
        self.assertAlmostEqual(position.unrealized_pnl, 161835)

    def test_missing_price_keeps_market_values_empty(self) -> None:
        result = calculate_portfolio(
            [PortfolioTransaction("2330", date(2026, 1, 2), "buy", 1000, 900, fee=100)]
        )

        position = result.positions[0]
        self.assertIsNone(position.latest_close)
        self.assertIsNone(position.market_value)
        self.assertIsNone(position.unrealized_pnl)
        self.assertIsNone(result.total_market_value)

    def test_selling_more_than_owned_is_rejected(self) -> None:
        with self.assertRaises(PortfolioCalculationError):
            calculate_portfolio(
                [
                    PortfolioTransaction("2330", date(2026, 1, 2), "buy", 100, 900),
                    PortfolioTransaction("2330", date(2026, 1, 3), "sell", 101, 910),
                ]
            )

    def test_closed_position_does_not_remain_in_holdings(self) -> None:
        result = calculate_portfolio(
            [
                PortfolioTransaction("2330", date(2026, 1, 2), "buy", 100, 900),
                PortfolioTransaction("2330", date(2026, 1, 3), "sell", 100, 910),
            ]
        )

        self.assertEqual(result.positions, [])
        self.assertAlmostEqual(result.realized_pnl, 1000)
        self.assertEqual(result.total_cost_basis, 0)


if __name__ == "__main__":
    unittest.main()
