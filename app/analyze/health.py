from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import pstdev

from app.models import DailyPrice


@dataclass(frozen=True, slots=True)
class TrendMetrics:
    latest_close: float | None
    close_20d_ago: float | None
    close_60d_ago: float | None
    change_20d_percent: float | None
    change_60d_percent: float | None


@dataclass(frozen=True, slots=True)
class PricePositionMetrics:
    latest_close: float | None
    high: float | None
    low: float | None
    position: float | None


@dataclass(frozen=True, slots=True)
class VolatilityMetrics:
    daily_return_std_percent: float | None
    max_daily_move_percent: float | None
    sample_days: int


@dataclass(frozen=True, slots=True)
class ProfitabilityMetrics:
    available: bool
    reason: str


@dataclass(frozen=True, slots=True)
class HealthMetrics:
    trend: TrendMetrics
    price_position: PricePositionMetrics
    profitability: ProfitabilityMetrics
    volatility: VolatilityMetrics


def calculate_health_metrics(prices: list[DailyPrice]) -> HealthMetrics:
    sorted_prices = sorted(_valid_prices(prices), key=lambda item: item.date)
    return HealthMetrics(
        trend=_calculate_trend(sorted_prices),
        price_position=_calculate_price_position(sorted_prices),
        profitability=ProfitabilityMetrics(
            available=False,
            reason="fundamental_data_not_synced",
        ),
        volatility=_calculate_volatility(sorted_prices),
    )


def _calculate_trend(prices: list[DailyPrice]) -> TrendMetrics:
    if not prices:
        return TrendMetrics(None, None, None, None, None)

    latest = prices[-1].close
    close_20d_ago = _close_n_trading_days_ago(prices, 20)
    close_60d_ago = _close_n_trading_days_ago(prices, 60)
    return TrendMetrics(
        latest_close=latest,
        close_20d_ago=close_20d_ago,
        close_60d_ago=close_60d_ago,
        change_20d_percent=_percent_change(close_20d_ago, latest),
        change_60d_percent=_percent_change(close_60d_ago, latest),
    )


def _calculate_price_position(prices: list[DailyPrice]) -> PricePositionMetrics:
    if not prices:
        return PricePositionMetrics(None, None, None, None)

    latest = prices[-1].close
    high = max(item.high for item in prices)
    low = min(item.low for item in prices)
    position = (latest - low) / (high - low) if high != low else None
    return PricePositionMetrics(
        latest_close=latest,
        high=high,
        low=low,
        position=position,
    )


def _calculate_volatility(prices: list[DailyPrice]) -> VolatilityMetrics:
    if len(prices) < 2:
        return VolatilityMetrics(None, None, 0)

    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous.close:
            returns.append(((current.close / previous.close) - 1) * 100)

    if not returns:
        return VolatilityMetrics(None, None, 0)

    return VolatilityMetrics(
        daily_return_std_percent=pstdev(returns),
        max_daily_move_percent=max(abs(item) for item in returns),
        sample_days=len(returns),
    )


def _close_n_trading_days_ago(prices: list[DailyPrice], days: int) -> float | None:
    if not prices:
        return None
    index = max(0, len(prices) - 1 - days)
    return prices[index].close


def _percent_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return ((end / start) - 1) * 100


def _valid_prices(prices: list[DailyPrice]) -> list[DailyPrice]:
    valid: list[DailyPrice] = []
    for item in prices or []:
        if not all(_positive_number(value) for value in (item.open, item.high, item.low, item.close)):
            continue
        if item.high < item.low or item.close < item.low or item.close > item.high:
            continue
        if item.volume == 0 and item.open == item.high == item.low == item.close:
            continue
        valid.append(item)
    return valid


def _positive_number(value: float | int | None) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0
