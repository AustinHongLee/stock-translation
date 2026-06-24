from __future__ import annotations

import math
import random

from app.analyze.structure_registry import (
    BAR_MAX,
    DIMENSION_SPECS,
    build_structure_payload,
    bar_level,
    sufficiency_grade,
)


def _random_walk_closes(n: int, *, seed: int = 11) -> list[float]:
    rng = random.Random(seed)
    out: list[float] = []
    level = math.log(100.0)
    for _ in range(n):
        level += rng.gauss(0, 0.015)
        out.append(math.exp(level))
    return out


def test_bar_level_bounds_and_clamp() -> None:
    spec = next(item for item in DIMENSION_SPECS if item.key == "memory")

    assert bar_level(spec, None) is None
    assert bar_level(spec, spec.bar_lo) == 0
    assert bar_level(spec, spec.bar_hi) == BAR_MAX
    assert bar_level(spec, spec.bar_lo - 10) == 0
    assert bar_level(spec, spec.bar_hi + 10) == BAR_MAX


def test_sufficiency_grade_uses_strictest_dimension() -> None:
    assert sufficiency_grade(300) == "high"
    assert sufficiency_grade(180) == "medium"
    assert sufficiency_grade(130) == "low"
    assert sufficiency_grade(50) == "insufficient"


def test_build_structure_payload_long_series_has_six_dimensions() -> None:
    payload = build_structure_payload(_random_walk_closes(360), as_of_date="2026-06-22")

    assert payload["available"] is True
    assert payload["title"] == "結構指紋"
    assert payload["as_of_date"] == "2026-06-22"
    assert payload["window"] == 250
    assert payload["sufficiency"]["grade"] == "high"
    assert len(payload["dimensions"]) == 6
    assert payload["dimensions"][-1]["key"] == "synchrony"
    assert payload["dimensions"][-1]["locked"] is True
    assert all(item["forbidden"] for item in payload["dimensions"])
    assert any(item["available"] for item in payload["dimensions"] if not item.get("locked"))
    assert all(item["grade"] == "high" for item in payload["dimensions"] if item.get("available"))


def test_build_structure_payload_short_series_degrades_without_exception() -> None:
    payload = build_structure_payload(_random_walk_closes(50), as_of_date="2026-06-22")

    assert payload["available"] is False
    assert payload["sufficiency"]["grade"] == "insufficient"
    assert len(payload["dimensions"]) == 6
    for item in payload["dimensions"]:
        if item.get("locked"):
            assert item["grade"] == "locked"
        else:
            assert item["available"] is False
            assert item["grade"] == "insufficient"
            assert item["bar_level"] is None
