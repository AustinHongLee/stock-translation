from __future__ import annotations

from app.analyze.relationships import build_relationships_payload


def _prices(closes: list[float]) -> list[dict[str, object]]:
    return [
        {
            "date": f"2026-06-{index + 1:02d}",
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000 + index * 10,
        }
        for index, close in enumerate(closes)
    ]


def _structure(*, complexity: int = 2, turbulence: int = 2, memory: int = 4, chroma: int = 3) -> dict[str, object]:
    return {
        "available": True,
        "dimensions": [
            {"key": "memory", "available": True, "bar_level": memory},
            {"key": "complexity", "available": True, "bar_level": complexity},
            {"key": "turbulence", "available": True, "bar_level": turbulence},
            {"key": "chroma", "available": True, "bar_level": chroma},
        ],
    }


def _payload(
    *,
    closes: list[float] | None = None,
    volume_ratios: list[float] | None = None,
    institutional: list[int] | None = None,
    structure: dict[str, object] | None = None,
) -> dict[str, object]:
    closes = closes or [100, 101, 102, 103, 104, 106]
    volume_ratios = volume_ratios or [1.0, 1.1, 1.25, 1.3, 1.35, 1.4]
    institutional = institutional if institutional is not None else [10, 20, 30, 40, 50, 60]
    return {
        "prices": _prices(closes),
        "features": {
            "available": True,
            "latest": {
                "volume_ratio": volume_ratios[-1],
                "macd": 1.2,
                "macd_signal": 0.9,
                "macd_histogram": 0.3,
                "bb_upper": 111,
                "bb_middle": 104,
                "bb_lower": 97,
                "bb_width": 8.1,
                "bb_position": 0.62,
                "kd_k": 56,
                "kd_d": 52,
                "ma5": 104,
                "ma20": 102,
                "ma60": 100,
            },
            "series": {"volume_ratio": volume_ratios},
        },
        "chips_series": [
            {"date": f"2026-06-{index + 1:02d}", "total_net": value}
            for index, value in enumerate(institutional)
        ],
        "structure": structure if structure is not None else _structure(),
        "revenue_summary": {"available": True, "facts": [{"label": "年增率", "value": 12.5}]},
        "financial_summary": {"available": True, "facts": [{"label": "EPS", "value": 3.2}]},
    }


def _item(payload: dict[str, object], key: str) -> dict[str, object]:
    result = build_relationships_payload(payload)
    return next(item for item in result["items"] if item["key"] == key)  # type: ignore[index]


def test_rising_price_with_volume_and_institutional_alignment_is_solid() -> None:
    item = _item(_payload(), "confirm_5d")

    assert item["group"] == "confirm"
    assert "比較扎實" in item["narration"]["plain"]  # type: ignore[index]
    assert "同向來源 2/2" in item["narration"]["detail"]  # type: ignore[index]
    assert item["reliability"] == "high"


def test_rising_price_with_dry_volume_is_discounted() -> None:
    item = _item(
        _payload(volume_ratios=[1.0, 0.75, 0.7, 0.68, 0.72, 0.7], institutional=[]),
        "confirm_5d",
    )

    assert "量不多" in item["narration"]["plain"]  # type: ignore[index]
    assert "同向來源 0/1" in item["narration"]["detail"]  # type: ignore[index]


def test_down_move_aligns_with_volume_and_institutional_outflow() -> None:
    item = _item(
        _payload(
            closes=[106, 105, 104, 103, 101, 99],
            volume_ratios=[1.0, 1.22, 1.28, 1.31, 1.4, 1.45],
            institutional=[10, -20, -30, -40, -50, -60],
        ),
        "confirm_5d",
    )

    assert "這次下跌有量、大戶也同步" in item["narration"]["plain"]  # type: ignore[index]
    assert "同向來源 2/2" in item["narration"]["detail"]  # type: ignore[index]


def test_noisy_structure_lowers_reliability_filter() -> None:
    result = build_relationships_payload(
        _payload(structure=_structure(complexity=5, turbulence=5, memory=2, chroma=1))
    )

    assert result["readability"]["level"] == "low"  # type: ignore[index]
    assert "很亂" in result["readability"]["plain"]  # type: ignore[index]
    confirm = next(item for item in result["items"] if item["key"] == "confirm_5d")  # type: ignore[index]
    assert confirm["reliability"] == "low"
