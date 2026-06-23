from __future__ import annotations

import json
import math
import unittest
from datetime import date, timedelta

from app.analyze.historical_frequency import (
    build_historical_frequency_report,
    summarize_forward_returns,
)
from app.news.classifier import contains_forbidden


def _sample_prices(days: int = 180) -> list[dict[str, object]]:
    start = date(2025, 1, 2)
    rows: list[dict[str, object]] = []
    for index in range(days):
        wave = math.sin(index / 5) * 3.5
        close = 50 + wave + index * 0.03
        open_price = close - (0.55 if index % 23 == 0 and index > 30 else 0.1)
        volume = 4500 if index % 23 == 0 and index > 30 else 1000 + (index % 5) * 30
        rows.append(
            {
                "date": start + timedelta(days=index),
                "open": round(open_price, 2),
                "high": round(close + 0.8, 2),
                "low": round(close - 0.9, 2),
                "close": round(close, 2),
                "volume": volume,
            }
        )
    return rows


class HistoricalFrequencyTests(unittest.TestCase):
    def test_summarize_forward_returns_fixed_distribution(self) -> None:
        summary = summarize_forward_returns([1, -1, 3, 5])

        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["positive_count"], 3)
        self.assertEqual(summary["positive_ratio_percent"], 75.0)
        self.assertEqual(summary["average_return_percent"], 2.0)
        self.assertEqual(summary["median_return_percent"], 2.0)
        self.assertAlmostEqual(summary["stdev_percent"], 2.58, delta=0.01)
        self.assertNotIn("normal_68_range_percent", summary)
        self.assertNotIn("normal_positive_area_percent", summary)

    def test_summarize_forward_returns_shows_normal_approximation_only_with_enough_samples(self) -> None:
        summary = summarize_forward_returns([-2, -1, 0.5, 1, 2, 3, 4, 5])

        self.assertEqual(summary["count"], 8)
        self.assertEqual(summary["normal_68_range_percent"], [-0.85, 3.97])
        self.assertEqual(summary["normal_95_range_percent"], [-3.16, 6.29])
        self.assertAlmostEqual(summary["normal_positive_area_percent"], 74.1, delta=0.1)

    def test_report_builds_event_windows_without_forbidden_language(self) -> None:
        report = build_historical_frequency_report(_sample_prices())

        self.assertTrue(report["available"])
        self.assertIn("不是未來機率", report["math_note"])
        self.assertGreaterEqual(len(report["events"]), 1)
        volume_event = next(item for item in report["events"] if item["key"] == "volume_up_day")
        self.assertGreater(volume_event["completed_sample_count"], 0)
        self.assertEqual([window["days"] for window in volume_event["windows"]], [5, 20])

        text = json.dumps(report, ensure_ascii=False)
        self.assertEqual(contains_forbidden(text), [])

    def test_insufficient_rows_returns_unavailable(self) -> None:
        report = build_historical_frequency_report(_sample_prices(30))

        self.assertFalse(report["available"])
        self.assertEqual(report["events"], [])


if __name__ == "__main__":
    unittest.main()
