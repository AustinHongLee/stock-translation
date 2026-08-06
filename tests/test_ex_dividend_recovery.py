from __future__ import annotations

import re
import unittest
from datetime import date, timedelta

from app.analyze.ex_dividend_recovery import build_ex_dividend_recovery
from app.models import DailyPrice, DividendRecord

FORBIDDEN = re.compile(
    r"會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|保證|必漲|必跌|明牌|買點|賣點|看多|看空"
)

TODAY = date(2026, 8, 6)


def _prices(rows: list[tuple[str, float]]) -> list[DailyPrice]:
    return [
        DailyPrice("2330", date.fromisoformat(day), close, close + 1, close - 1, close, 1000)
        for day, close in rows
    ]


def _ex_record(ex_day: str, cash: float) -> DividendRecord:
    ex = date.fromisoformat(ex_day)
    return DividendRecord(
        stock_id="2330",
        year=ex.year - 1911,
        period=f"除息 {ex:%m/%d}",
        status="除息",
        board_date=ex,
        shareholder_meeting_date=None,
        cash_dividend=cash,
        stock_dividend=0.0,
        source="TWSE_TWT49U",
    )


def _announce_record(board_day: str, cash: float) -> DividendRecord:
    return DividendRecord(
        stock_id="2330",
        year=2026 - 1911,
        period="第1季",
        status="董事會決議",
        board_date=date.fromisoformat(board_day),
        shareholder_meeting_date=None,
        cash_dividend=cash,
        stock_dividend=0.0,
        source="TWSE_T187AP45",
    )


def _daily_walk(start: str, closes: list[float]) -> list[tuple[str, float]]:
    day = date.fromisoformat(start)
    rows: list[tuple[str, float]] = []
    for close in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append((day.isoformat(), close))
        day += timedelta(days=1)
    return rows


class ExDividendRecoveryTests(unittest.TestCase):
    def test_filled_event_counts_trading_days(self) -> None:
        # 基準 100（7/1），7/2 除息跌到 96，7/6 回到 100 → 第 3 個交易日填息
        prices = _prices(
            [
                ("2026-07-01", 100.0),
                ("2026-07-02", 96.0),
                ("2026-07-03", 98.0),
                ("2026-07-06", 100.5),
                ("2026-07-07", 101.0),
            ]
        )
        result = build_ex_dividend_recovery(prices, [_ex_record("2026-07-02", 4.0)], today=TODAY)

        self.assertTrue(result["available"])
        event = result["events"][0]
        self.assertEqual(event["base_close"], 100.0)
        self.assertTrue(event["filled"])
        self.assertEqual(event["fill_date"], "2026-07-06")
        self.assertEqual(event["fill_trading_days"], 3)
        self.assertEqual(result["stats"]["filled_count"], 1)
        self.assertEqual(result["stats"]["fill_rate_percent"], 100.0)

    def test_same_day_fill_is_one_trading_day(self) -> None:
        prices = _prices(
            [("2026-06-30", 99.0), ("2026-07-01", 100.0), ("2026-07-02", 100.2)]
        )
        result = build_ex_dividend_recovery(prices, [_ex_record("2026-07-02", 4.0)], today=TODAY)
        self.assertEqual(result["events"][0]["fill_trading_days"], 1)

    def test_unfilled_after_one_year_is_settled_false(self) -> None:
        rows = [("2025-06-30", 100.0)] + _daily_walk("2025-07-01", [90.0] * 260)
        prices = _prices(rows)
        result = build_ex_dividend_recovery(prices, [_ex_record("2025-07-01", 5.0)], today=TODAY)

        event = result["events"][0]
        self.assertIs(event["filled"], False)
        self.assertEqual(result["stats"]["events_count"], 1)
        self.assertEqual(result["stats"]["filled_count"], 0)
        self.assertEqual(result["stats"]["fill_rate_percent"], 0.0)

    def test_window_truncated_by_next_ex_dividend(self) -> None:
        # 季配：第一次除息後一直沒回基準價，下一次除息把窗口截斷 → 該次終局未填
        rows = [("2026-01-05", 100.0)] + _daily_walk("2026-01-06", [95.0] * 60)
        last_day = rows[-1][0]
        next_ex = (date.fromisoformat(last_day) + timedelta(days=1)).isoformat()
        rows += _daily_walk(next_ex, [94.0] * 10)
        prices = _prices(rows)
        dividends = [_ex_record("2026-01-06", 3.0), _ex_record(next_ex, 3.0)]
        result = build_ex_dividend_recovery(prices, dividends, today=TODAY)

        first = result["events"][0]
        self.assertIs(first["filled"], False)
        self.assertTrue(first["window_truncated_by_next_ex"])

    def test_ongoing_event_reports_gap_not_verdict(self) -> None:
        prices = _prices(
            [
                ("2026-07-30", 100.0),
                ("2026-07-31", 95.0),
                ("2026-08-03", 96.0),
                ("2026-08-04", 97.0),
            ]
        )
        result = build_ex_dividend_recovery(prices, [_ex_record("2026-07-31", 5.0)], today=TODAY)

        event = result["events"][0]
        self.assertIsNone(event["filled"])
        self.assertAlmostEqual(event["current_gap_percent"], 3.0)
        self.assertIsNotNone(result["ongoing"])
        self.assertIn("還沒回到除息前價位", result["note"])

    def test_announcement_records_are_ignored(self) -> None:
        prices = _prices([("2026-07-01", 100.0), ("2026-07-02", 96.0)])
        result = build_ex_dividend_recovery(prices, [_announce_record("2026-05-12", 4.0)], today=TODAY)
        self.assertFalse(result["available"])
        self.assertIn("除息紀錄", result["reason"])

    def test_long_suspension_before_ex_date_skips_event(self) -> None:
        prices = _prices(
            [
                ("2026-05-01", 100.0),  # 基準距除息 61 天 → 排除
                ("2026-07-01", 96.0),
                ("2026-07-02", 97.0),
                ("2026-07-03", 98.0),
            ]
        )
        result = build_ex_dividend_recovery(prices, [_ex_record("2026-07-01", 4.0)], today=TODAY)
        self.assertFalse(result["available"])

    def test_texts_pass_forbidden_scan(self) -> None:
        prices = _prices(
            [
                ("2026-07-01", 100.0),
                ("2026-07-02", 96.0),
                ("2026-07-03", 100.5),
                ("2026-07-30", 101.0),
                ("2026-07-31", 95.0),
            ]
        )
        dividends = [_ex_record("2026-07-02", 4.0), _ex_record("2026-07-31", 5.0)]
        result = build_ex_dividend_recovery(prices, dividends, today=TODAY)
        for text in (result["note"], result["disclaimer"]):
            self.assertIsNone(FORBIDDEN.search(str(text)), f"forbidden word in: {text}")


if __name__ == "__main__":
    unittest.main()
