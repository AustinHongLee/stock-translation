from __future__ import annotations

from dataclasses import dataclass

from app.models import DailyPrice


@dataclass(frozen=True, slots=True)
class PriceSummary:
    rows: int
    start_date: str | None
    end_date: str | None
    latest_close: float | None
    previous_close: float | None
    change: float | None
    change_percent: float | None
    change_source: str | None
    change_note: str | None
    high: float | None
    low: float | None
    price_position: float | None


def calculate_price_summary(prices: list[DailyPrice]) -> PriceSummary:
    if not prices:
        return PriceSummary(
            rows=0,
            start_date=None,
            end_date=None,
            latest_close=None,
            previous_close=None,
            change=None,
            change_percent=None,
            change_source=None,
            change_note=None,
            high=None,
            low=None,
            price_position=None,
        )

    sorted_prices = sorted(prices, key=lambda item: item.date)
    latest = sorted_prices[-1]
    previous = sorted_prices[-2] if len(sorted_prices) >= 2 else None
    high = max(item.high for item in sorted_prices)
    low = min(item.low for item in sorted_prices)
    raw_change = latest.close - previous.close if previous else None
    change = latest.change if latest.change is not None else raw_change
    change_source = "twse_change" if latest.change is not None else "close_to_close"
    change_percent = (
        (change / previous.close) * 100
        if previous and previous.close
        else None
    )
    price_position = (
        (latest.close - low) / (high - low)
        if high != low
        else None
    )

    return PriceSummary(
        rows=len(sorted_prices),
        start_date=sorted_prices[0].date.isoformat(),
        end_date=latest.date.isoformat(),
        latest_close=latest.close,
        previous_close=previous.close if previous else None,
        change=change,
        change_percent=change_percent,
        change_source=change_source,
        change_note=_change_note(latest),
        high=high,
        low=low,
        price_position=price_position,
    )


def _change_note(price: DailyPrice) -> str | None:
    if "change_marker=" not in price.note:
        return None
    marker = price.note.split("change_marker=", 1)[1].split(";", 1)[0].strip()
    if not marker:
        return None
    return f"TWSE 日線漲跌含 {marker} 標記，可能是除權息或特殊交易日；不要用前一天收盤硬減判斷單日漲跌。"
