from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from app.portfolio.models import PortfolioPosition, PortfolioResult, PortfolioTransaction


class PortfolioCalculationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    close: float
    date: date


@dataclass(slots=True)
class _WorkingPosition:
    shares: int = 0
    cost_basis: float = 0.0

    @property
    def average_cost(self) -> float:
        if self.shares <= 0:
            return 0.0
        return self.cost_basis / self.shares


def calculate_portfolio(
    transactions: list[PortfolioTransaction],
    latest_prices: Mapping[str, PriceSnapshot | None] | None = None,
) -> PortfolioResult:
    latest_prices = latest_prices or {}
    sorted_transactions = sorted(
        transactions,
        key=lambda item: (item.trade_date, item.id or 0),
    )
    positions: dict[str, _WorkingPosition] = {}
    realized_pnl = 0.0

    for transaction in sorted_transactions:
        _validate_transaction(transaction)
        stock_id = transaction.stock_id.strip()
        position = positions.setdefault(stock_id, _WorkingPosition())
        if transaction.side == "buy":
            buy_cost = transaction.shares * transaction.price + transaction.fee
            position.shares += transaction.shares
            position.cost_basis += buy_cost
            continue

        if transaction.shares > position.shares:
            raise PortfolioCalculationError(
                f"{stock_id} sell shares exceed current holdings on {transaction.trade_date}"
            )
        matched_cost = transaction.shares * position.average_cost
        sell_proceeds = transaction.shares * transaction.price - transaction.fee - transaction.tax
        realized_pnl += sell_proceeds - matched_cost
        position.shares -= transaction.shares
        position.cost_basis -= matched_cost
        if position.shares == 0:
            position.cost_basis = 0.0

    result_positions = [
        _build_position(stock_id, position, latest_prices.get(stock_id))
        for stock_id, position in sorted(positions.items())
        if position.shares > 0
    ]
    total_cost_basis = sum(item.cost_basis for item in result_positions)
    market_values = [item.market_value for item in result_positions]
    total_market_value = (
        sum(value for value in market_values if value is not None)
        if market_values and all(value is not None for value in market_values)
        else None
    )
    total_unrealized_pnl = (
        total_market_value - total_cost_basis
        if total_market_value is not None
        else None
    )
    total_unrealized_return_percent = (
        (total_unrealized_pnl / total_cost_basis) * 100
        if total_unrealized_pnl is not None and total_cost_basis
        else None
    )

    return PortfolioResult(
        positions=result_positions,
        transactions=sorted_transactions,
        realized_pnl=round(realized_pnl, 4),
        total_cost_basis=round(total_cost_basis, 4),
        total_market_value=_round_or_none(total_market_value),
        total_unrealized_pnl=_round_or_none(total_unrealized_pnl),
        total_unrealized_return_percent=_round_or_none(total_unrealized_return_percent),
    )


def _build_position(
    stock_id: str,
    position: _WorkingPosition,
    latest_price: PriceSnapshot | None,
) -> PortfolioPosition:
    market_value = (
        position.shares * latest_price.close
        if latest_price is not None
        else None
    )
    unrealized_pnl = (
        market_value - position.cost_basis
        if market_value is not None
        else None
    )
    unrealized_return_percent = (
        (unrealized_pnl / position.cost_basis) * 100
        if unrealized_pnl is not None and position.cost_basis
        else None
    )
    return PortfolioPosition(
        stock_id=stock_id,
        shares=position.shares,
        average_cost=round(position.average_cost, 4),
        cost_basis=round(position.cost_basis, 4),
        latest_close=latest_price.close if latest_price else None,
        latest_close_date=latest_price.date if latest_price else None,
        market_value=_round_or_none(market_value),
        unrealized_pnl=_round_or_none(unrealized_pnl),
        unrealized_return_percent=_round_or_none(unrealized_return_percent),
    )


def _validate_transaction(transaction: PortfolioTransaction) -> None:
    if not transaction.stock_id.strip():
        raise PortfolioCalculationError("stock_id is required")
    if transaction.side not in {"buy", "sell"}:
        raise PortfolioCalculationError("side must be buy or sell")
    if transaction.shares <= 0:
        raise PortfolioCalculationError("shares must be positive")
    if transaction.price < 0:
        raise PortfolioCalculationError("price cannot be negative")
    if transaction.fee < 0 or transaction.tax < 0:
        raise PortfolioCalculationError("fee and tax cannot be negative")


def _round_or_none(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
