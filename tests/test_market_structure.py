from __future__ import annotations

import random

from app.analyze.cross_section import ReturnsMatrix
from app.analyze.market_structure import (
    average_pairwise_correlation,
    correlation_matrix,
    cross_sectional_dispersion,
    largest_eigenvalue_power,
    market_mode_share,
)


def _matrix_from_columns(columns: list[list[float]]) -> ReturnsMatrix:
    rows = [[columns[col][row] for col in range(len(columns))] for row in range(len(columns[0]))]
    return ReturnsMatrix(
        stock_ids=[f"S{idx:03d}" for idx in range(len(columns))],
        dates=[f"2026-06-{idx + 1:02d}" for idx in range(len(rows))],
        returns=rows,
    )


def _independent_matrix(stocks: int = 24, days: int = 240, seed: int = 7) -> ReturnsMatrix:
    rng = random.Random(seed)
    return _matrix_from_columns([[rng.gauss(0, 0.015) for _ in range(days)] for _ in range(stocks)])


def _single_factor_matrix(stocks: int = 24, days: int = 240, seed: int = 7) -> ReturnsMatrix:
    rng = random.Random(seed)
    factor = [rng.gauss(0, 0.018) for _ in range(days)]
    columns = []
    for _ in range(stocks):
        beta = 0.85 + rng.random() * 0.3
        columns.append([beta * f + rng.gauss(0, 0.006) for f in factor])
    return _matrix_from_columns(columns)


def _synchronized_matrix(stocks: int = 24, days: int = 240, seed: int = 7) -> ReturnsMatrix:
    rng = random.Random(seed)
    base = [rng.gauss(0, 0.015) for _ in range(days)]
    columns = [[value + rng.gauss(0, 0.0005) for value in base] for _ in range(stocks)]
    return _matrix_from_columns(columns)


def test_independent_returns_have_low_average_correlation_and_mode_share() -> None:
    matrix = _independent_matrix()

    herding = average_pairwise_correlation(matrix)
    synchrony = market_mode_share(matrix)
    dispersion = cross_sectional_dispersion(matrix)

    assert herding.available
    assert synchrony.available
    assert dispersion.available
    assert abs(herding.value or 0) < 0.08
    assert (synchrony.value or 0) < 0.16
    assert dispersion.value is not None and dispersion.value > 0


def test_single_factor_returns_raise_correlation_and_market_mode() -> None:
    independent = _independent_matrix()
    factor = _single_factor_matrix()

    assert (average_pairwise_correlation(factor).value or 0) > 0.55
    assert (market_mode_share(factor).value or 0) > 0.6
    assert (market_mode_share(factor).value or 0) > (market_mode_share(independent).value or 0)


def test_synchronized_returns_approach_one_correlation_and_mode_share() -> None:
    matrix = _synchronized_matrix()

    assert (average_pairwise_correlation(matrix).value or 0) > 0.99
    assert (market_mode_share(matrix).value or 0) > 0.99


def test_correlation_matrix_is_symmetric_with_unit_diagonal() -> None:
    corr = correlation_matrix(_single_factor_matrix(stocks=5, days=80))

    assert len(corr) == 5
    for i in range(5):
        assert abs(corr[i][i] - 1.0) < 1e-12
        for j in range(5):
            assert abs(corr[i][j] - corr[j][i]) < 1e-12


def test_power_iteration_matches_known_largest_eigenvalue() -> None:
    matrix = [
        [2.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 0.5],
    ]

    assert abs(largest_eigenvalue_power(matrix) - 2.0) < 1e-8
