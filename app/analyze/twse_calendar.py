from __future__ import annotations

from datetime import date, timedelta

# Source: Taiwan Stock Exchange holiday schedule for 2026.
# Keep this small and explicit until a live holiday CSV ingestion exists.
TWSE_NON_TRADING_DATES_2026 = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 2, 12),
        date(2026, 2, 13),
        date(2026, 2, 16),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 2, 20),
        date(2026, 2, 27),
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 5, 1),
        date(2026, 6, 19),
        date(2026, 9, 25),
        date(2026, 9, 28),
        date(2026, 10, 9),
        date(2026, 10, 26),
        date(2026, 12, 25),
    }
)

TWSE_EXTRA_TRADING_DATES = frozenset[date]()
TWSE_NON_TRADING_DATES = TWSE_NON_TRADING_DATES_2026


def is_twse_trading_day(day: date) -> bool:
    if day in TWSE_EXTRA_TRADING_DATES:
        return True
    if day in TWSE_NON_TRADING_DATES:
        return False
    return day.weekday() < 5


def count_twse_trading_days(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        return 0
    total = 0
    current = start_date
    while current <= end_date:
        if is_twse_trading_day(current):
            total += 1
        current += timedelta(days=1)
    return total


def previous_twse_trading_day(day: date) -> date:
    current = day
    while not is_twse_trading_day(current):
        current -= timedelta(days=1)
    return current


def next_twse_trading_day(day: date) -> date:
    current = day
    while not is_twse_trading_day(current):
        current += timedelta(days=1)
    return current
