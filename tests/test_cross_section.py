from __future__ import annotations

import math

from app.analyze.cross_section import build_returns_matrix


def _series(stock_offset: float, days: int = 8, *, missing: set[int] | None = None) -> list[tuple[str, float]]:
    missing = missing or set()
    return [
        (f"2026-06-{day + 1:02d}", 100 + stock_offset + day)
        for day in range(days)
        if day not in missing
    ]


def test_build_returns_matrix_aligns_common_dates_and_returns() -> None:
    matrix = build_returns_matrix(
        {
            "2330": _series(0, 8),
            "2303": _series(10, 8, missing={1}),
            "2317": _series(20, 8, missing={2}),
        },
        window=6,
        min_stocks=3,
        min_days=5,
    )

    assert matrix is not None
    assert matrix.stock_ids == ["2303", "2317", "2330"]
    assert matrix.dates == ["2026-06-04", "2026-06-05", "2026-06-06", "2026-06-07", "2026-06-08"]
    assert len(matrix.returns) == 5
    assert all(len(row) == 3 for row in matrix.returns)
    expected = math.log(113 / 110)
    assert abs(matrix.returns[0][0] - expected) < 1e-12


def test_build_returns_matrix_returns_none_when_stock_count_insufficient() -> None:
    matrix = build_returns_matrix(
        {"2330": _series(0, 8), "2303": _series(10, 8)},
        min_stocks=3,
        min_days=5,
    )

    assert matrix is None


def test_build_returns_matrix_returns_none_when_common_days_insufficient() -> None:
    matrix = build_returns_matrix(
        {
            "2330": _series(0, 8, missing={0, 1, 2, 3}),
            "2303": _series(10, 8, missing={4, 5, 6}),
            "2317": _series(20, 8),
        },
        min_stocks=3,
        min_days=5,
    )

    assert matrix is None


def test_build_returns_matrix_takes_recent_window_after_intersection() -> None:
    matrix = build_returns_matrix(
        {
            "2330": _series(0, 10),
            "2303": _series(10, 10, missing={0}),
            "2317": _series(20, 10, missing={1}),
        },
        window=5,
        min_stocks=3,
        min_days=5,
    )

    assert matrix is not None
    assert matrix.dates == ["2026-06-07", "2026-06-08", "2026-06-09", "2026-06-10"]
