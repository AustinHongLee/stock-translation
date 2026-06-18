from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from app.models import DailyPrice, DividendRecord
from app.portfolio.calculator import PriceSnapshot
from app.portfolio.models import PortfolioResult, PortfolioTransaction


@dataclass(frozen=True, slots=True)
class CashDividendEvent:
    stock_id: str
    ex_date: date
    shares: int
    cash_dividend_per_share: float
    cash_amount: float
    source: str


@dataclass(frozen=True, slots=True)
class BenchmarkPerformance:
    symbol: str
    name: str
    total_return_amount: float | None
    total_return_percent: float | None
    xirr_percent: float | None
    latest_value: float | None
    latest_date: date | None
    status: str
    note: str


@dataclass(frozen=True, slots=True)
class PortfolioPerformance:
    cash_dividend_events: list[CashDividendEvent]
    total_cash_dividends: float
    total_return_amount: float | None
    total_return_percent: float | None
    xirr_percent: float | None
    benchmark: BenchmarkPerformance | None
    dividend_data_complete: bool
    notes: list[str]


def calculate_portfolio_performance(
    *,
    portfolio: PortfolioResult,
    transactions: Sequence[PortfolioTransaction],
    dividends_by_stock: Mapping[str, Sequence[DividendRecord]],
    latest_prices: Mapping[str, PriceSnapshot | None],
    benchmark_prices: Sequence[DailyPrice] | None = None,
    benchmark_symbol: str = "0050",
    benchmark_name: str = "0050",
) -> PortfolioPerformance:
    sorted_transactions = sorted(transactions, key=lambda item: (item.trade_date, item.id or 0))
    dividend_events, dividend_complete = _cash_dividend_events(
        sorted_transactions,
        dividends_by_stock,
    )
    total_cash_dividends = round(sum(item.cash_amount for item in dividend_events), 4)

    total_return_amount = None
    total_return_percent = None
    if portfolio.total_unrealized_pnl is not None:
        total_return_amount = round(
            portfolio.total_unrealized_pnl + portfolio.realized_pnl + total_cash_dividends,
            4,
        )
        if portfolio.total_cost_basis:
            total_return_percent = round(total_return_amount / portfolio.total_cost_basis * 100, 4)

    cashflows = _portfolio_cashflows(
        sorted_transactions,
        dividend_events,
        portfolio=portfolio,
    )
    xirr_percent = _round_or_none(_xirr(cashflows), scale=100)

    benchmark = None
    if benchmark_prices is not None:
        benchmark = _benchmark_performance(
            sorted_transactions,
            benchmark_prices,
            benchmark_symbol=benchmark_symbol,
            benchmark_name=benchmark_name,
        )

    notes: list[str] = [
        "含息總報酬已納入可辨識除息日的現金股利；股票股利與稅務尚未納入。",
        "XIRR 會把投入與領回的時間納入計算；資料不足時不顯示。",
    ]
    if not dividend_complete:
        notes.append("部分股票缺少可辨識除息日的官方配息資料，累計現金股利可能偏低。")
    if benchmark is None or benchmark.status != "available":
        notes.append("0050 對比需要本地已有 0050 日線資料，尚未同步時會先留空。")

    return PortfolioPerformance(
        cash_dividend_events=dividend_events,
        total_cash_dividends=total_cash_dividends,
        total_return_amount=total_return_amount,
        total_return_percent=total_return_percent,
        xirr_percent=xirr_percent,
        benchmark=benchmark,
        dividend_data_complete=dividend_complete,
        notes=notes,
    )


def _cash_dividend_events(
    transactions: Sequence[PortfolioTransaction],
    dividends_by_stock: Mapping[str, Sequence[DividendRecord]],
) -> tuple[list[CashDividendEvent], bool]:
    events: list[CashDividendEvent] = []
    dividend_complete = True
    traded_stock_ids = sorted({item.stock_id for item in transactions})
    for stock_id in traded_stock_ids:
        records = list(dividends_by_stock.get(stock_id) or [])
        actual_records = [
            item
            for item in records
            if item.source == "TWSE_TWT49U"
            and item.board_date is not None
            and item.cash_dividend > 0
        ]
        if not actual_records:
            dividend_complete = False
            continue
        for record in sorted(actual_records, key=lambda item: item.board_date or date.min):
            ex_date = record.board_date
            if ex_date is None:
                continue
            shares = _shares_before_date(transactions, stock_id, ex_date)
            if shares <= 0:
                continue
            events.append(
                CashDividendEvent(
                    stock_id=stock_id,
                    ex_date=ex_date,
                    shares=shares,
                    cash_dividend_per_share=round(record.cash_dividend, 6),
                    cash_amount=round(shares * record.cash_dividend, 4),
                    source=record.source,
                )
            )
    return sorted(events, key=lambda item: (item.ex_date, item.stock_id)), dividend_complete


def _shares_before_date(
    transactions: Sequence[PortfolioTransaction],
    stock_id: str,
    target_date: date,
) -> int:
    shares = 0
    for transaction in transactions:
        if transaction.stock_id != stock_id or transaction.trade_date >= target_date:
            continue
        if transaction.side == "buy":
            shares += transaction.shares
        else:
            shares -= transaction.shares
    return max(shares, 0)


def _portfolio_cashflows(
    transactions: Sequence[PortfolioTransaction],
    dividend_events: Sequence[CashDividendEvent],
    *,
    portfolio: PortfolioResult,
) -> list[tuple[date, float]]:
    flows: list[tuple[date, float]] = []
    for transaction in transactions:
        if transaction.side == "buy":
            flows.append(
                (
                    transaction.trade_date,
                    -(transaction.shares * transaction.price + transaction.fee),
                )
            )
        else:
            flows.append(
                (
                    transaction.trade_date,
                    transaction.shares * transaction.price - transaction.fee - transaction.tax,
                )
            )
    flows.extend((event.ex_date, event.cash_amount) for event in dividend_events)
    terminal_value = portfolio.total_market_value
    terminal_date = _latest_position_date(portfolio)
    if terminal_value is not None and terminal_value > 0 and terminal_date is not None:
        flows.append((terminal_date, terminal_value))
    return flows


def _latest_position_date(portfolio: PortfolioResult) -> date | None:
    dates = [
        position.latest_close_date
        for position in portfolio.positions
        if position.latest_close_date is not None
    ]
    return max(dates) if dates else None


def _benchmark_performance(
    transactions: Sequence[PortfolioTransaction],
    benchmark_prices: Sequence[DailyPrice],
    *,
    benchmark_symbol: str,
    benchmark_name: str,
) -> BenchmarkPerformance:
    if not transactions:
        return BenchmarkPerformance(
            symbol=benchmark_symbol,
            name=benchmark_name,
            total_return_amount=None,
            total_return_percent=None,
            xirr_percent=None,
            latest_value=None,
            latest_date=None,
            status="not_applicable",
            note="尚無交易紀錄可比較。",
        )
    if not benchmark_prices:
        return BenchmarkPerformance(
            symbol=benchmark_symbol,
            name=benchmark_name,
            total_return_amount=None,
            total_return_percent=None,
            xirr_percent=None,
            latest_value=None,
            latest_date=None,
            status="missing_data",
            note=f"尚未同步 {benchmark_symbol} 日線資料，暫時不能做大盤對比。",
        )

    prices = sorted(benchmark_prices, key=lambda item: item.date)
    units = 0.0
    invested = 0.0
    withdrawn = 0.0
    flows: list[tuple[date, float]] = []
    for transaction in transactions:
        price = _price_on_or_before(prices, transaction.trade_date)
        if price is None or price.close <= 0:
            return BenchmarkPerformance(
                symbol=benchmark_symbol,
                name=benchmark_name,
                total_return_amount=None,
                total_return_percent=None,
                xirr_percent=None,
                latest_value=None,
                latest_date=None,
                status="missing_data",
                note=f"{benchmark_symbol} 缺少 {transaction.trade_date} 前後的日線資料。",
            )
        if transaction.side == "buy":
            cash = transaction.shares * transaction.price + transaction.fee
            invested += cash
            units += cash / price.close
            flows.append((transaction.trade_date, -cash))
        else:
            cash = transaction.shares * transaction.price - transaction.fee - transaction.tax
            withdrawn += cash
            units = max(0.0, units - cash / price.close)
            flows.append((transaction.trade_date, cash))

    latest = prices[-1]
    latest_value = units * latest.close
    if latest_value > 0:
        flows.append((latest.date, latest_value))
    total_return_amount = withdrawn + latest_value - invested
    total_return_percent = total_return_amount / invested * 100 if invested else None

    return BenchmarkPerformance(
        symbol=benchmark_symbol,
        name=benchmark_name,
        total_return_amount=round(total_return_amount, 4),
        total_return_percent=_round_or_none(total_return_percent),
        xirr_percent=_round_or_none(_xirr(flows), scale=100),
        latest_value=round(latest_value, 4),
        latest_date=latest.date,
        status="available",
        note=f"用相同投入與提款時點，換成 {benchmark_symbol} 收盤價做對照。",
    )


def _price_on_or_before(prices: Sequence[DailyPrice], target_date: date) -> DailyPrice | None:
    found = None
    for price in prices:
        if price.date <= target_date:
            found = price
        else:
            break
    return found


def _xirr(cashflows: Sequence[tuple[date, float]]) -> float | None:
    flows = [(flow_date, amount) for flow_date, amount in cashflows if amount]
    if len(flows) < 2:
        return None
    if not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        return None
    start = min(flow_date for flow_date, _ in flows)

    def npv(rate: float) -> float:
        total = 0.0
        for flow_date, amount in flows:
            years = (flow_date - start).days / 365
            total += amount / ((1 + rate) ** years)
        return total

    low = -0.9999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)
    for _ in range(6):
        if low_value * high_value <= 0:
            break
        high *= 10
        high_value = npv(high)
    if low_value * high_value > 0:
        return None

    for _ in range(120):
        mid = (low + high) / 2
        mid_value = npv(mid)
        if abs(mid_value) < 1e-7:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2


def _round_or_none(value: float | None, *, scale: float = 1.0) -> float | None:
    if value is None:
        return None
    return round(value * scale, 4)

