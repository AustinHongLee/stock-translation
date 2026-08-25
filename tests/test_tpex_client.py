from __future__ import annotations

import unittest
from datetime import date

from app.sync.tpex import TpexClient, TpexError


def _trading_stock_payload(rows: list[list[str]]) -> dict:
    return {
        "stat": "ok",
        "date": "20260701",
        "tables": [
            {
                "fields": [
                    "日 期",
                    "成交仟股",
                    "成交仟元",
                    "開盤",
                    "最高",
                    "最低",
                    "收盤",
                    "漲跌",
                    "筆數",
                ],
                "data": rows,
            }
        ],
    }


class TpexTradingStockTests(unittest.TestCase):
    """golden：上櫃日線的民國日期與「仟股/仟元 ×1000」單位轉換（tpex-評估 實測欄位）。"""

    def test_month_rows_convert_thousand_units(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("tradingStock", url)
            self.assertIn("code=3105", url)
            return _trading_stock_payload(
                [["115/07/01", "1,234", "45,678", "36.00", "37.10", "35.50", "37.00", "+0.85", "890"]]
            )

        client = TpexClient(fetch_json=fake_fetch_json, request_interval=0)
        prices = client.fetch_daily_prices_for_month("3105", date(2026, 7, 1))

        self.assertEqual(len(prices), 1)
        price = prices[0]
        self.assertEqual(price.date, date(2026, 7, 1))
        self.assertEqual(price.volume, 1_234_000)  # 仟股 ×1000
        self.assertEqual(price.trade_value, 45_678_000)  # 仟元 ×1000
        self.assertEqual(price.close, 37.0)
        self.assertEqual(price.change, 0.85)
        self.assertEqual(price.transaction_count, 890)
        self.assertEqual(price.source, "TPEX_TRADING_STOCK")

    def test_not_ok_stat_returns_empty(self) -> None:
        client = TpexClient(
            fetch_json=lambda url: {"stat": "查無資料", "tables": []}, request_interval=0
        )
        self.assertEqual(client.fetch_daily_prices_for_month("3105", date(2026, 7, 1)), [])

    def test_all_rows_unparsable_raises(self) -> None:
        client = TpexClient(
            fetch_json=lambda url: _trading_stock_payload([["garbage"], ["also", "bad"]]),
            request_interval=0,
        )
        with self.assertRaises(TpexError):
            client.fetch_daily_prices_for_month("3105", date(2026, 7, 1))

    def test_fetch_daily_prices_streams_on_month(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> object:
            month = url.split("date=", 1)[1].split("&", 1)[0][:7]
            calls.append(month)
            roc = "115/08/01" if "2026%2F08" in url else "115/07/01"
            return _trading_stock_payload(
                [[roc, "1,000", "36,000", "36.00", "36.50", "35.50", "36.00", "0.00", "100"]]
            )

        batches: list[list] = []
        client = TpexClient(fetch_json=fake_fetch_json, request_interval=0)
        prices = client.fetch_daily_prices(
            "3105", date(2026, 7, 1), date(2026, 8, 31), on_month=batches.append
        )
        self.assertEqual(len(batches), 2)
        self.assertEqual([p.date for p in prices], [date(2026, 7, 1), date(2026, 8, 1)])


class TpexDailyQuotesTests(unittest.TestCase):
    @staticmethod
    def _payload(rows: list[list[str]], *, response_date: str = "20260804") -> dict:
        return {
            "stat": "ok",
            "date": response_date,
            "tables": [
                {
                    "title": "上櫃股票行情",
                    "fields": [
                        "代號",
                        "名稱",
                        "收盤",
                        "漲跌",
                        "開盤",
                        "最高",
                        "最低",
                        "均價",
                        "成交股數",
                        "成交金額(元)",
                        "成交筆數",
                    ],
                    "data": rows,
                }
            ],
        }

    def test_all_market_day_filters_stocks_and_keeps_share_units(self) -> None:
        payload = self._payload(
            [
                ["3105", "穩懋", "37.00", "+0.85", "36.00", "37.10", "35.50", "36.9", "1,234,000", "45,678,000", "890"],
                ["01001T", "不在股票清單", "10", "0", "10", "10", "10", "10", "3,000", "30,000", "2"],
            ]
        )
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)

        prices = client.fetch_all_daily_prices_for_date(
            date(2026, 8, 4), stock_ids={"3105"}
        )

        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].stock_id, "3105")
        self.assertEqual(prices[0].volume, 1_234_000)
        self.assertEqual(prices[0].trade_value, 45_678_000)
        self.assertEqual(prices[0].source, "TPEX_DAILY_QUOTES")

    def test_response_date_mismatch_raises(self) -> None:
        client = TpexClient(
            fetch_json=lambda url: self._payload([], response_date="20260803"),
            request_interval=0,
        )
        with self.assertRaises(TpexError):
            client.fetch_all_daily_prices_for_date(date(2026, 8, 4))

    def test_empty_holiday_returns_empty(self) -> None:
        client = TpexClient(
            fetch_json=lambda url: self._payload([], response_date="20260804"),
            request_interval=0,
        )
        self.assertEqual(client.fetch_all_daily_prices_for_date(date(2026, 8, 4)), [])


class TpexOpenApiTests(unittest.TestCase):
    def test_otc_profiles_map_market_and_listed_date(self) -> None:
        payload = [
            {
                "SecuritiesCompanyCode": "3105",
                "CompanyName": "穩懋半導體股份有限公司",
                "CompanyAbbreviation": "穩懋",
                "SecuritiesIndustryCode": "24",
                "DateOfListing": "19991216",
            },
            {"CompanyName": "沒有代號的列會被跳過"},
        ]
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)
        profiles = client.fetch_otc_profiles()

        self.assertEqual(len(profiles), 1)
        profile = profiles[0]
        self.assertEqual(profile.stock_id, "3105")
        self.assertEqual(profile.market, "TPEX")
        self.assertEqual(profile.short_name, "穩懋")
        self.assertEqual(profile.listed_date, date(1999, 12, 16))

    def test_otc_profiles_field_drift_raises_instead_of_silent_empty(self) -> None:
        payload = [{"TotallyDifferentKey": "3105"}]
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)
        with self.assertRaises(TpexError):
            client.fetch_otc_profiles()

    def test_mainboard_quotes_parse_and_unit_self_check(self) -> None:
        payload = [
            {
                # 單位正確（股/元）
                "SecuritiesCompanyCode": "3105",
                "Date": "1150804",
                "Open": "36.00",
                "High": "37.10",
                "Low": "35.50",
                "Close": "37.00",
                "Change": "0.85",
                "TradingShares": "1234000",
                "TransactionAmount": "45678000",
                "TransactionNumber": "890",
            },
            {
                # shares 被「仟股」小報 1000 倍 → 自校驗 ×1000
                "SecuritiesCompanyCode": "5347",
                "Date": "1150804",
                "Open": "50.0",
                "High": "51.0",
                "Low": "49.0",
                "Close": "50.0",
                "Change": "0.00",
                "TradingShares": "1234",
                "TransactionAmount": "61700000",
                "TransactionNumber": "10",
            },
        ]
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)
        prices = client.fetch_latest_all_prices()

        self.assertEqual(len(prices), 2)
        first = prices[0]
        self.assertEqual(first.date, date(2026, 8, 4))
        self.assertEqual(first.volume, 1_234_000)
        self.assertEqual(first.source, "TPEX_MAINBOARD_QUOTES")
        second = prices[1]
        self.assertEqual(second.volume, 1_234_000)  # 1234 仟股 → 1,234,000 股
        self.assertEqual(second.trade_value, 61_700_000)

    def test_mainboard_quotes_field_drift_raises(self) -> None:
        client = TpexClient(fetch_json=lambda url: [{"Weird": "x"}], request_interval=0)
        with self.assertRaises(TpexError):
            client.fetch_latest_all_prices()

    def test_peratio_alias_maps_to_market_valuation(self) -> None:
        payload = [
            {
                "SecuritiesCompanyCode": "3105",
                "Date": "1150804",
                "PriceEarningRatio": "18.5",
                "DividendYield": "3.2",
                "PriceBookRatio": "2.1",
            }
        ]
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)
        valuation = client.fetch_market_valuation("3105")

        assert valuation is not None
        self.assertEqual(valuation.pe_ratio, 18.5)
        self.assertEqual(valuation.dividend_yield, 3.2)
        self.assertEqual(valuation.pb_ratio, 2.1)
        self.assertEqual(valuation.date, date(2026, 8, 4))

    def test_monthly_revenue_reuses_twse_chinese_schema(self) -> None:
        payload = [
            {
                "公司代號": "3105",
                "公司名稱": "穩懋",
                "產業別": "24",
                "資料年月": "11507",
                "營業收入-當月營收": "1,000,000",
                "營業收入-上月營收": "900,000",
                "營業收入-去年當月營收": "800,000",
                "營業收入-上月比較增減(%)": "11.1",
                "營業收入-去年同月增減(%)": "25.0",
                "累計營業收入-當月累計營收": "7,000,000",
                "累計營業收入-去年累計營收": "6,000,000",
                "累計營業收入-前期比較增減(%)": "16.7",
                "出表日期": "1150810",
                "備註": "-",
            }
        ]
        client = TpexClient(fetch_json=lambda url: payload, request_interval=0)
        revenue = client.fetch_monthly_revenue("3105")

        assert revenue is not None
        self.assertEqual(revenue.year_month, "2026-07")
        self.assertEqual(revenue.current_month_revenue, 1_000_000)
        self.assertEqual(revenue.yoy_percent, 25.0)


if __name__ == "__main__":
    unittest.main()
