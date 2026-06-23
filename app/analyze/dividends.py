from __future__ import annotations

import re
from datetime import date

from app.models import DividendRecord

SOURCE_EX_DIVIDEND = "TWSE_TWT49U"
SOURCE_ANNOUNCEMENT = "TWSE_T187AP45"
DIVIDEND_HISTORY_YEARS = 6


def dividend_history_start_date(end_date: date, years: int = DIVIDEND_HISTORY_YEARS) -> date:
    if years < 1:
        raise ValueError("years must be positive")
    return date(end_date.year - years + 1, 1, 1)


def dedupe_dividend_records(records: list[DividendRecord]) -> list[DividendRecord]:
    """Merge TWSE announcement rows with ex-dividend rows without double counting paid events."""
    ex_cash_by_year: dict[tuple[str, int], list[float]] = {}
    has_ex_by_year: set[tuple[str, int]] = set()
    for record in records:
        if record.source == SOURCE_EX_DIVIDEND:
            key = (record.stock_id, record.year)
            has_ex_by_year.add(key)
            if record.cash_dividend > 0:
                ex_cash_by_year.setdefault(key, []).append(record.cash_dividend)

    by_key: dict[tuple[str, int, str], DividendRecord] = {}
    for record in records:
        if record.cash_dividend <= 0 and record.stock_dividend <= 0:
            continue
        year_key = (record.stock_id, record.year)
        if record.source == SOURCE_ANNOUNCEMENT and year_key in has_ex_by_year:
            if is_annual_period(record.period):
                continue
            paid_amounts = ex_cash_by_year.get(year_key, [])
            if any(abs(record.cash_dividend - paid_amount) < 0.01 for paid_amount in paid_amounts):
                continue

        key = (record.stock_id, record.year, record.period)
        current = by_key.get(key)
        if current is None or _source_priority(record.source) > _source_priority(current.source):
            by_key[key] = record
    return sorted(
        by_key.values(),
        key=lambda item: (item.stock_id, item.year, item.period),
        reverse=True,
    )


def annual_cash_dividends_by_year(records: list[DividendRecord]) -> dict[int, float]:
    annual_values: dict[int, float] = {}
    by_year: dict[int, list[DividendRecord]] = {}
    for record in records:
        if record.cash_dividend > 0 or record.stock_dividend > 0:
            by_year.setdefault(record.year, []).append(record)

    for year, year_records in by_year.items():
        ex_dividend_records = [item for item in year_records if item.source == SOURCE_EX_DIVIDEND]
        if ex_dividend_records:
            paid_cash = sum(item.cash_dividend for item in ex_dividend_records)
            announcement_cash = sum(
                item.cash_dividend
                for item in year_records
                if item.source != SOURCE_EX_DIVIDEND and not is_annual_period(item.period)
            )
            annual_values[year] = paid_cash + announcement_cash
            continue

        annual_records = [item for item in year_records if is_annual_period(item.period)]
        if annual_records:
            annual_values[year] = sum(item.cash_dividend for item in annual_records)
            continue

        quarter_records = [item for item in year_records if is_quarter_period(item.period)]
        if len(quarter_records) >= 4:
            annual_values[year] = sum(item.cash_dividend for item in quarter_records)
    return annual_values


def recent_annual_cash_values(
    annual_cash_by_year: dict[int, float],
    historical_years: int,
) -> list[float]:
    if historical_years < 1:
        return []
    return [
        annual_cash_by_year[year]
        for year in sorted(annual_cash_by_year, reverse=True)[:historical_years]
    ]


def is_annual_period(period: str) -> bool:
    text = str(period or "").strip()
    return text == "年度" or bool(re.fullmatch(r"\d{2,3}", text))


def is_quarter_period(period: str) -> bool:
    text = str(period or "").strip()
    return "季" in text or bool(re.fullmatch(r"\d{2,3}Q[1-4]", text, flags=re.IGNORECASE))


def _source_priority(source: str) -> int:
    if source == SOURCE_EX_DIVIDEND:
        return 3
    if source == SOURCE_ANNOUNCEMENT:
        return 2
    return 1
