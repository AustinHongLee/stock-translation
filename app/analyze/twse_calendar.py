from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

# Source: TWSE official holiday schedule endpoint:
# https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule
#
# The official schedule contains both non-trading rows and marker rows such as
# "first trading day" / "last trading day".  Keep the parsed exceptions here so
# gap checks stay fast and deterministic while tests lock the parsing rules.
TWSE_HOLIDAY_SCHEDULE_URL = "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule"
TWSE_OPENAPI_HOLIDAY_SCHEDULE_URL = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"

TWSE_NON_TRADING_DATES_BY_YEAR = {
    2024: frozenset(
        {
            date(2024, 1, 1),
            date(2024, 2, 6),
            date(2024, 2, 7),
            date(2024, 2, 8),
            date(2024, 2, 9),
            date(2024, 2, 10),
            date(2024, 2, 11),
            date(2024, 2, 12),
            date(2024, 2, 13),
            date(2024, 2, 14),
            date(2024, 2, 28),
            date(2024, 4, 4),
            date(2024, 4, 5),
            date(2024, 5, 1),
            date(2024, 6, 10),
            date(2024, 9, 17),
            date(2024, 10, 10),
        }
    ),
    2025: frozenset(
        {
            date(2025, 1, 1),
            date(2025, 1, 23),
            date(2025, 1, 24),
            date(2025, 1, 27),
            date(2025, 1, 28),
            date(2025, 1, 29),
            date(2025, 1, 30),
            date(2025, 1, 31),
            date(2025, 2, 28),
            date(2025, 4, 3),
            date(2025, 4, 4),
            date(2025, 5, 1),
            date(2025, 5, 30),
            date(2025, 5, 31),
            date(2025, 9, 28),
            date(2025, 9, 29),
            date(2025, 10, 6),
            date(2025, 10, 10),
            date(2025, 10, 24),
            date(2025, 10, 25),
            date(2025, 12, 25),
        }
    ),
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 2, 12),
            date(2026, 2, 13),
            date(2026, 2, 15),
            date(2026, 2, 16),
            date(2026, 2, 17),
            date(2026, 2, 18),
            date(2026, 2, 19),
            date(2026, 2, 20),
            date(2026, 2, 27),
            date(2026, 2, 28),
            date(2026, 4, 3),
            date(2026, 4, 4),
            date(2026, 4, 5),
            date(2026, 4, 6),
            date(2026, 5, 1),
            date(2026, 6, 19),
            date(2026, 9, 25),
            date(2026, 9, 28),
            date(2026, 10, 9),
            date(2026, 10, 10),
            date(2026, 10, 25),
            date(2026, 10, 26),
            date(2026, 12, 25),
        }
    ),
}

TWSE_EXTRA_TRADING_DATES = frozenset(
    {
        date(2024, 1, 2),
        date(2024, 2, 5),
        date(2024, 2, 15),
        date(2025, 1, 2),
        date(2025, 1, 22),
        date(2025, 2, 3),
        date(2026, 1, 2),
        date(2026, 2, 11),
        date(2026, 2, 23),
    }
)
TWSE_NON_TRADING_DATES = frozenset().union(*TWSE_NON_TRADING_DATES_BY_YEAR.values())
TWSE_HOLIDAY_YEARS = frozenset(TWSE_NON_TRADING_DATES_BY_YEAR)

_TRADING_MARKER_TEXT = ("開始交易", "最後交易")


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


def parse_twse_holiday_schedule_rows(rows: Iterable[object]) -> tuple[frozenset[date], frozenset[date]]:
    """Classify official TWSE holiday rows into non-trading and trading markers.

    Supports both the RWD JSON rows ([date, name, description]) and the OpenAPI
    rows ({"Date": "1150101", "Name": "...", "Description": "..."}).
    """
    non_trading: set[date] = set()
    extra_trading: set[date] = set()
    for row in rows:
        row_date, name, description = _holiday_row_fields(row)
        day = parse_twse_schedule_date(row_date)
        marker_text = f"{name} {description}"
        if any(item in marker_text for item in _TRADING_MARKER_TEXT):
            extra_trading.add(day)
        else:
            non_trading.add(day)
    return frozenset(non_trading), frozenset(extra_trading)


def parse_twse_schedule_date(raw: object) -> date:
    text = str(raw).strip().replace("/", "-")
    if "-" in text:
        return date.fromisoformat(text)
    if len(text) == 7 and text.isdigit():
        year = int(text[:3]) + 1911
        return date(year, int(text[3:5]), int(text[5:7]))
    if len(text) == 8 and text.isdigit():
        year = int(text[:4])
        if year >= 1900:
            return date(year, int(text[4:6]), int(text[6:8]))
        return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))
    raise ValueError(f"unsupported TWSE holiday date: {raw!r}")


def _holiday_row_fields(row: object) -> tuple[object, str, str]:
    if isinstance(row, dict):
        return (
            row.get("Date") or row.get("日期") or "",
            str(row.get("Name") or row.get("名稱") or ""),
            str(row.get("Description") or row.get("說明") or ""),
        )
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return (
            row[0],
            str(row[1]),
            str(row[2]) if len(row) >= 3 else "",
        )
    raise ValueError(f"unsupported TWSE holiday row: {row!r}")
