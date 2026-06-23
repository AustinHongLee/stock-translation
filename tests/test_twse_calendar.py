from __future__ import annotations

import unittest
from datetime import date

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
