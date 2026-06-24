"""Cross-section helpers for market-level structure analysis."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReturnsMatrix:
    stock_ids: list[str]
    dates: list[str]
    returns: list[list[float]]

    def to_json(self) -> dict[str, Any]:
        return {
            "stock_ids": list(self.stock_ids),
            "dates": list(self.dates),
            "returns": [list(row) for row in self.returns],
        }


def build_returns_matrix(
    series_by_stock: dict[str, list[tuple[str, float]]],
    *,
    window: int = 120,
    min_stocks: int = 30,
    min_days: int = 60,
) -> ReturnsMatrix | None:
    """Align close series on common dates and return a dense log-return matrix."""
    cleaned = {
        stock_id: _clean_series(series)
        for stock_id, series in (series_by_stock or {}).items()
        if stock_id
    }
    cleaned = {stock_id: series for stock_id, series in cleaned.items() if len(series) >= min_days}
    if len(cleaned) < min_stocks:
        return None

    common_dates: set[str] | None = None
    for series in cleaned.values():
        dates = {date for date, _ in series}
        common_dates = dates if common_dates is None else common_dates & dates
    if not common_dates:
        return None

    selected_dates = sorted(common_dates)[-max(2, int(window)):]
    if len(selected_dates) < min_days:
        return None

    keep_ids: list[str] = []
    close_columns: list[list[float]] = []
    for stock_id in sorted(cleaned):
        by_date = dict(cleaned[stock_id])
        closes: list[float] = []
        ok = True
        for day in selected_dates:
            close = by_date.get(day)
            if close is None or close <= 0:
                ok = False
                break
            closes.append(close)
        if ok:
            keep_ids.append(stock_id)
            close_columns.append(closes)

    if len(keep_ids) < min_stocks:
        return None

    return_dates = selected_dates[1:]
    rows: list[list[float]] = []
    for row_idx in range(1, len(selected_dates)):
        row: list[float] = []
        for closes in close_columns:
            previous = closes[row_idx - 1]
            current = closes[row_idx]
            if previous <= 0 or current <= 0:
                return None
            row.append(math.log(current / previous))
        rows.append(row)

    if len(rows) < max(1, min_days - 1):
        return None
    return ReturnsMatrix(stock_ids=keep_ids, dates=return_dates, returns=rows)


def _clean_series(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    by_date: dict[str, float] = {}
    for raw_date, raw_close in series or []:
        day = str(raw_date or "").strip()
        if not day:
            continue
        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            continue
        if math.isfinite(close) and close > 0:
            by_date[day] = close
    return sorted(by_date.items())
