from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

PortfolioSide = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class PortfolioTransaction:
    stock_id: str
    trade_date: date
    side: PortfolioSide
    shares: int
    price: float
    fee: float = 0.0
    tax: float = 0.0
    note: str = ""
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    stock_id: str
    shares: int
    average_cost: float
    cost_basis: float
    latest_close: float | None
    latest_close_date: date | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_return_percent: float | None


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    positions: list[PortfolioPosition]
    transactions: list[PortfolioTransaction]
    realized_pnl: float
    total_cost_basis: float
    total_market_value: float | None
    total_unrealized_pnl: float | None
    total_unrealized_return_percent: float | None
