from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class StockProfile:
    stock_id: str
    name: str
    short_name: str
    industry_code: str | None = None
    market: str = "TWSE"
    listed_date: date | None = None
    source_updated_at: date | None = None


@dataclass(frozen=True, slots=True)
class DailyPrice:
    stock_id: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    trade_value: int | None = None
    transaction_count: int | None = None
    change: float | None = None
    note: str = ""
    source: str = "TWSE"


@dataclass(frozen=True, slots=True)
class DividendRecord:
    stock_id: str
    year: int
    period: str
    status: str
    board_date: date | None
    shareholder_meeting_date: date | None
    cash_dividend: float
    stock_dividend: float
    source_updated_at: date | None = None
    note: str = ""
    source: str = "TWSE_T187AP45"


@dataclass(frozen=True, slots=True)
class MarketValuation:
    stock_id: str
    date: date
    pe_ratio: float | None
    dividend_yield: float | None
    pb_ratio: float | None
    source: str = "TWSE_BWIBBU_ALL"


@dataclass(frozen=True, slots=True)
class MonthlyRevenue:
    stock_id: str
    year_month: str
    company_name: str
    industry: str
    current_month_revenue: int
    previous_month_revenue: int | None
    last_year_month_revenue: int | None
    mom_percent: float | None
    yoy_percent: float | None
    cumulative_revenue: int | None
    cumulative_last_year_revenue: int | None
    cumulative_yoy_percent: float | None
    source_updated_at: date | None = None
    note: str = ""
    source: str = "TWSE_T187AP05_L"


@dataclass(frozen=True, slots=True)
class FinancialStatement:
    stock_id: str
    year: int
    quarter: int
    company_name: str
    revenue: int | None
    gross_profit: int | None
    operating_income: int | None
    non_operating_income_expense: int | None
    pre_tax_income: int | None
    net_income: int | None
    parent_net_income: int | None
    eps: float | None
    total_assets: int | None
    total_liabilities: int | None
    parent_equity: int | None
    total_equity: int | None
    book_value_per_share: float | None
    source_updated_at: date | None = None
    source: str = "TWSE_T187AP06_07_L_CI"


@dataclass(frozen=True, slots=True)
class IntradayQuote:
    stock_id: str
    name: str
    full_name: str
    trade_datetime: datetime | None
    current_price: float | None
    previous_close: float | None
    open_price: float | None
    high_price: float | None
    low_price: float | None
    volume: int | None
    best_bid_price: float | None
    best_ask_price: float | None
    bid_prices: tuple[float, ...] = ()
    ask_prices: tuple[float, ...] = ()
    source: str = "TWSE_MIS"
    source_delay_ms: int | None = None


@dataclass(frozen=True, slots=True)
class InstitutionalTrade:
    """三大法人單日買賣超（股數）。正值＝買超、負值＝賣超。資料源：TWSE T86。"""

    stock_id: str
    date: date
    foreign_net: int  # 外陸資買賣超(不含外資自營商)
    trust_net: int    # 投信買賣超
    dealer_net: int   # 自營商買賣超(合計)
    total_net: int    # 三大法人買賣超
    source: str = "TWSE_T86"
