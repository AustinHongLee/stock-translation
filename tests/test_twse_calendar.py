from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.analyze.twse_calendar import (
    TWSE_EXTRA_TRADING_DATES,
    TWSE_HOLIDAY_YEARS,
    TWSE_NON_TRADING_DATES,
    count_twse_trading_days,
    is_twse_trading_day,
    parse_twse_holiday_schedule_rows,
    parse_twse_schedule_date,
    previous_twse_trading_day,
)


class TwseCalendarTests(unittest.TestCase):
    def test_calendar_covers_multiple_official_years(self) -> None:
        self.assertGreaterEqual(TWSE_HOLIDAY_YEARS, {2024, 2025, 2026})
        self.assertFalse(is_twse_trading_day(date(2024, 2, 8)))
        self.assertFalse(is_twse_trading_day(date(2025, 1, 27)))
        self.assertFalse(is_twse_trading_day(date(2026, 6, 19)))

    def test_official_trading_markers_do_not_become_holidays(self) -> None:
        self.assertIn(date(2026, 2, 11), TWSE_EXTRA_TRADING_DATES)
        self.assertTrue(is_twse_trading_day(date(2026, 2, 11)))
        self.assertTrue(is_twse_trading_day(date(2026, 2, 23)))

    def test_official_weekend_holidays_remain_non_trading(self) -> None:
        self.assertIn(date(2026, 2, 15), TWSE_NON_TRADING_DATES)
        self.assertFalse(is_twse_trading_day(date(2026, 2, 15)))

    def test_count_skips_2025_lunar_new_year_holidays(self) -> None:
        self.assertEqual(count_twse_trading_days(date(2025, 1, 22), date(2025, 2, 3)), 2)
        self.assertEqual(previous_twse_trading_day(date(2025, 2, 2)), date(2025, 1, 22))

    def test_parse_official_rwd_rows(self) -> None:
        non_trading, extra_trading = parse_twse_holiday_schedule_rows(
            [
                ["2026-01-02", "國曆新年開始交易日", "國曆新年開始交易。"],
                ["2026-02-12", "市場無交易，僅辦理結算交割作業", ""],
                ["2026-02-16", "農曆除夕及春節", "依規定放假。"],
            ]
        )

        self.assertEqual(extra_trading, frozenset({date(2026, 1, 2)}))
        self.assertEqual(non_trading, frozenset({date(2026, 2, 12), date(2026, 2, 16)}))

    def test_parse_official_openapi_rows_and_roc_dates(self) -> None:
        self.assertEqual(parse_twse_schedule_date("1150227"), date(2026, 2, 27))
        non_trading, extra_trading = parse_twse_holiday_schedule_rows(
            [
                {
                    "Name": "農曆春節前最後交易日",
                    "Date": "1150211",
                    "Weekday": "三",
                    "Description": "農曆春節前最後交易。",
                },
                {
                    "Name": "和平紀念日",
                    "Date": "1150227",
                    "Weekday": "五",
                    "Description": "補假。",
                },
            ]
        )

        self.assertEqual(extra_trading, frozenset({date(2026, 2, 11)}))
        self.assertEqual(non_trading, frozenset({date(2026, 2, 27)}))


if __name__ == "__main__":
    unittest.main()


class CountTradingDaysPrefixSumTests(unittest.TestCase):
    """count_twse_trading_days 前綴和快速路徑必須與逐日迴圈完全等價。"""

    @staticmethod
    def _naive_count(start: date, end: date) -> int:
        total = 0
        current = start
        while current <= end:
            if is_twse_trading_day(current):
                total += 1
            current += timedelta(days=1)
        return total

    def test_equivalent_across_holiday_windows(self) -> None:
        windows = [
            (date(2026, 7, 1), date(2026, 7, 6)),      # 本次診斷的洞窗口
            (date(2026, 2, 10), date(2026, 2, 25)),    # 春節長假 + 補班日
            (date(2025, 12, 20), date(2026, 1, 5)),    # 跨年
            (date(2024, 1, 1), date(2026, 12, 31)),    # 跨三個官方年度
            (date(2026, 7, 4), date(2026, 7, 5)),      # 純週末 → 0
        ]
        for start, end in windows:
            with self.subTest(start=start, end=end):
                self.assertEqual(
                    count_twse_trading_days(start, end),
                    self._naive_count(start, end),
                )

    def test_single_day_and_reversed_range(self) -> None:
        trading = date(2026, 7, 9)
        weekend = date(2026, 7, 5)
        self.assertEqual(count_twse_trading_days(trading, trading), 1)
        self.assertEqual(count_twse_trading_days(weekend, weekend), 0)
        self.assertEqual(count_twse_trading_days(trading, trading - timedelta(days=1)), 0)

    def test_windows_outside_prefix_range_fall_back(self) -> None:
        # 早於前綴和起點的窗口走逐日 fallback，仍要等價。
        start, end = date(2019, 12, 25), date(2020, 1, 10)
        self.assertEqual(count_twse_trading_days(start, end), self._naive_count(start, end))
        # 完全在範圍外（過去）
        start, end = date(2018, 1, 1), date(2018, 1, 31)
        self.assertEqual(count_twse_trading_days(start, end), self._naive_count(start, end))
