from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.analyze.dividends import (
    annual_cash_dividends_by_year as _annual_cash_dividends_by_year,
    recent_annual_cash_values as _recent_annual_cash_values,
)
from app.models import DailyPrice, DividendRecord, MarketValuation


@dataclass(frozen=True, slots=True)
class DividendSummary:
    rows: int
    average_cash_dividend: float | None
    latest_cash_dividend: float | None
    latest_stock_dividend: float | None
    years: list[int]
    estimate_source: str
    stock_dividend_scope_note: str | None = None


@dataclass(frozen=True, slots=True)
class YieldPriceEstimate:
    scenario: str
    target_yield_percent: float
    price: float | None


@dataclass(frozen=True, slots=True)
class HistoricalYieldPoint:
    year: int
    cash_dividend: float
    average_close: float
    yield_percent: float


@dataclass(frozen=True, slots=True)
class HistoricalYieldValuation:
    years: list[HistoricalYieldPoint]
    average_yield_percent: float | None
    high_yield_percent: float | None
    low_yield_percent: float | None
    estimates: list[YieldPriceEstimate]
    latest_close: float | None
    cheap_difference: float | None
    cheap_difference_percent: float | None
    price_basis: str


@dataclass(frozen=True, slots=True)
class ValuationResult:
    dividend_summary: DividendSummary
    estimates: list[YieldPriceEstimate]
    historical_yield: HistoricalYieldValuation | None
    market: MarketValuation | None
    confidence: str
    suitability_notes: list[str]
    warning: str


def calculate_dividend_valuation(
    dividends: list[DividendRecord],
    market: MarketValuation | None,
    latest_close: float | None = None,
    prices: list[DailyPrice] | None = None,
    historical_years: int = 5,
    listed_date: date | None = None,
) -> ValuationResult:
    relevant = [item for item in dividends if item.cash_dividend > 0 or item.stock_dividend > 0]
    annual_cash_by_year = _annual_cash_dividends_by_year(relevant)
    annual_values = _recent_annual_cash_values(annual_cash_by_year, historical_years)
    if annual_values:
        average_cash = sum(annual_values) / len(annual_values)
        estimate_source = "annual_dividend_records"
    elif market and market.dividend_yield and latest_close:
        average_cash = latest_close * (market.dividend_yield / 100)
        estimate_source = "market_yield_implied"
    else:
        average_cash = None
        estimate_source = "insufficient_data"
    latest = relevant[0] if relevant else None
    estimates = [
        _estimate("high_yield", average_cash, 6.25),
        _estimate("average_yield", average_cash, 5.0),
        _estimate("low_yield", average_cash, 3.125),
    ]
    historical_yield = _historical_yield_valuation(
        annual_cash_by_year=annual_cash_by_year,
        annual_cash_dividend=average_cash,
        prices=prices or [],
        latest_close=latest_close,
        historical_years=historical_years,
    )
    as_of_date = max((item.date for item in prices or []), default=date.today())
    confidence, suitability_notes = _valuation_confidence(
        average_cash=average_cash,
        latest_close=latest_close,
        annual_years_count=len(annual_values),
        market=market,
        listed_date=listed_date,
        as_of_date=as_of_date,
    )
    return ValuationResult(
        dividend_summary=DividendSummary(
            rows=len(relevant),
            average_cash_dividend=average_cash,
            latest_cash_dividend=latest.cash_dividend if latest else None,
            latest_stock_dividend=latest.stock_dividend if latest else None,
            years=sorted({item.year for item in relevant}, reverse=True),
            estimate_source=estimate_source,
            stock_dividend_scope_note=_stock_dividend_scope_note(relevant),
        ),
        estimates=estimates,
        historical_yield=historical_yield,
        market=market,
        confidence=confidence,
        suitability_notes=suitability_notes,
        warning="股利殖利率情境只用股利與歷史價格回推，不代表交易基準價格，也不預測股價。",
    )


def _stock_dividend_scope_note(dividends: list[DividendRecord]) -> str | None:
    if any(item.source == "TWSE_TWT49U" for item in dividends):
        return (
            "股票股利只納入公告資料；TWSE TWT49U 歷史除權息僅用息值作現金股利，"
            "權值不是每股股票股利。"
        )
    return None


def _estimate(
    scenario: str,
    average_cash_dividend: float | None,
    target_yield_percent: float,
) -> YieldPriceEstimate:
    price = (
        average_cash_dividend / (target_yield_percent / 100)
        if average_cash_dividend is not None and target_yield_percent > 0
        else None
    )
    return YieldPriceEstimate(scenario=scenario, target_yield_percent=target_yield_percent, price=price)


def _historical_yield_valuation(
    *,
    annual_cash_by_year: dict[int, float],
    annual_cash_dividend: float | None,
    prices: list[DailyPrice],
    latest_close: float | None,
    historical_years: int,
) -> HistoricalYieldValuation | None:
    if annual_cash_dividend is None or historical_years < 1:
        return None

    prices_by_roc_year: dict[int, list[DailyPrice]] = {}
    for price in prices:
        prices_by_roc_year.setdefault(price.date.year - 1911, []).append(price)

    points: list[HistoricalYieldPoint] = []
    for year in sorted(annual_cash_by_year, reverse=True):
        if len(points) >= historical_years:
            break
        year_prices = prices_by_roc_year.get(year, [])
        closes = [item.close for item in year_prices if item.close > 0]
        if not closes:
            continue
        average_close = sum(closes) / len(closes)
        cash_dividend = annual_cash_by_year[year]
        if average_close <= 0 or cash_dividend <= 0:
            continue
        points.append(
            HistoricalYieldPoint(
                year=year,
                cash_dividend=cash_dividend,
                average_close=average_close,
                yield_percent=(cash_dividend / average_close) * 100,
            )
        )

    if not points:
        points = _estimated_historical_yield_points(
            prices_by_roc_year=prices_by_roc_year,
            annual_cash_dividend=annual_cash_dividend,
            historical_years=historical_years,
        )
        price_basis = "官方殖利率反推估計年股利 / 各年度日收盤均價"
    else:
        price_basis = "股利年度日收盤均價"

    if not points:
        return None

    yields = [item.yield_percent for item in points]
    average_yield = sum(yields) / len(yields)
    high_yield = max(yields)
    low_yield = min(yields)
    estimates = [
        _estimate("high_yield", annual_cash_dividend, high_yield),
        _estimate("average_yield", annual_cash_dividend, average_yield),
        _estimate("low_yield", annual_cash_dividend, low_yield),
    ]
    cheap_price = estimates[0].price
    cheap_difference = (
        latest_close - cheap_price
        if latest_close is not None and cheap_price is not None
        else None
    )
    cheap_difference_percent = (
        (cheap_difference / cheap_price) * 100
        if cheap_difference is not None and cheap_price
        else None
    )
    return HistoricalYieldValuation(
        years=points,
        average_yield_percent=average_yield,
        high_yield_percent=high_yield,
        low_yield_percent=low_yield,
        estimates=estimates,
        latest_close=latest_close,
        cheap_difference=cheap_difference,
        cheap_difference_percent=cheap_difference_percent,
        price_basis=price_basis,
    )


def _estimated_historical_yield_points(
    *,
    prices_by_roc_year: dict[int, list[DailyPrice]],
    annual_cash_dividend: float,
    historical_years: int,
) -> list[HistoricalYieldPoint]:
    points: list[HistoricalYieldPoint] = []
    if annual_cash_dividend <= 0:
        return points

    for year in sorted(prices_by_roc_year, reverse=True):
        if len(points) >= historical_years:
            break
        closes = [item.close for item in prices_by_roc_year[year] if item.close > 0]
        if not closes:
            continue
        average_close = sum(closes) / len(closes)
        if average_close <= 0:
            continue
        points.append(
            HistoricalYieldPoint(
                year=year,
                cash_dividend=annual_cash_dividend,
                average_close=average_close,
                yield_percent=(annual_cash_dividend / average_close) * 100,
            )
        )
    return points


def _valuation_confidence(
    *,
    average_cash: float | None,
    latest_close: float | None,
    annual_years_count: int,
    market: MarketValuation | None,
    listed_date: date | None,
    as_of_date: date,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    confidence = "medium" if average_cash is not None else "low"

    if average_cash is None:
        notes.append("缺少可年化的現金股利，股利法估價暫時不能當主要判斷。")
        return confidence, notes

    if annual_years_count < 3:
        confidence = "low"
        notes.append(f"只有 {annual_years_count} 個發放年度，還不到 3 年，近 5 年平均股利不穩。")
    elif annual_years_count < 5:
        confidence = "medium"
        notes.append(f"目前只有 {annual_years_count} 個發放年度，還不是完整 5 年樣本。")
    else:
        confidence = "high"

    if listed_date is not None and (as_of_date - listed_date).days < 365 * 3:
        confidence = "low"
        notes.append("上市時間未滿 3 年，價格區間與股利紀錄都還短，估價要降權看。")

    implied_yield = (
        (average_cash / latest_close) * 100
        if latest_close and latest_close > 0
        else None
    )
    market_yield = market.dividend_yield if market else None
    low_yield = implied_yield is not None and implied_yield < 1
    low_market_yield = market_yield is not None and market_yield < 1
    if low_yield or low_market_yield:
        confidence = "low"
        notes.append("殖利率低於 1%，固定目標殖利率情境會把反推價格壓得很低，這類股票更像成長股或題材股，不能只看股利法。")

    return confidence, notes
