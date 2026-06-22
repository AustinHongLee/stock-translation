from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.analyze.watchlist_board import build_watchlist_board_item
from app.models import DailyPrice


class WatchlistBoardTests(unittest.TestCase):
    def test_board_item_reports_latest_change_assessment_and_local_risk(self) -> None:
        prices = _prices(date(2026, 3, 1), [50 + i * 0.5 for i in range(80)])

        item = build_watchlist_board_item(
            "2330",
            {"short_name": "台積電"},
            prices,
            today=date(2026, 5, 20),
        )

        self.assertEqual(item["name"], "台積電")
        self.assertEqual(item["latest"]["date"], "2026-05-19")  # type: ignore[index]
        self.assertAlmostEqual(item["latest"]["change"], 0.5)  # type: ignore[index]
        self.assertGreater(item["latest"]["change_percent"], 0)  # type: ignore[index]
        self.assertIn(item["assessment"]["tone"], {"positive", "neutral", "caution"})  # type: ignore[index]
        self.assertIn("status", item["level"])
        self.assertEqual(item["risk"]["source"], "local_only")  # type: ignore[index]
        self.assertIn("新聞地雷需進個股頁抓取", item["disclaimer"])

    def test_stale_or_missing_data_is_explicit(self) -> None:
        stale = build_watchlist_board_item(
            "2330",
            None,
            _prices(date(2026, 1, 1), [10, 11, 12]),
            today=date(2026, 6, 22),
        )
        missing = build_watchlist_board_item("2330", None, [], today=date(2026, 6, 22))

        self.assertEqual(stale["risk"]["label"], "資料過期")  # type: ignore[index]
        self.assertEqual(stale["risk"]["tone"], "caution")  # type: ignore[index]
        self.assertEqual(missing["risk"]["label"], "資料不足")  # type: ignore[index]
        self.assertEqual(missing["latest"]["close"], None)  # type: ignore[index]


def _prices(start: date, closes: list[float]) -> list[DailyPrice]:
    return [
        DailyPrice(
            stock_id="2330",
            date=start + timedelta(days=index),
            open=close - 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1_000_000 + index,
        )
        for index, close in enumerate(closes)
    ]


if __name__ == "__main__":
    unittest.main()
