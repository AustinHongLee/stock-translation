from __future__ import annotations

import unittest
from datetime import date

from app.sync.twse import TwseClient, TwseError


class TwseClientTests(unittest.TestCase):
    def test_fetch_daily_prices_for_month_normalizes_twse_stock_day_rows(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("STOCK_DAY", url)
            return {
                "stat": "OK",
                "data": [
                    [
                        "115/06/01",
                        "60,942,792",
                        "144,105,259,583",
                        "2,355.00",
                        "2,415.00",
                        "2,350.00",
                        "2,355.00",
                        " 0.00",
                        "136,367",
                        "",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json)
        prices = client.fetch_daily_prices_for_month("2330", date(2026, 6, 1))

        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].date, date(2026, 6, 1))
        self.assertEqual(prices[0].volume, 60942792)
        self.assertEqual(prices[0].trade_value, 144105259583)
        self.assertEqual(prices[0].open, 2355.0)
        self.assertEqual(prices[0].close, 2355.0)

    def test_fetch_daily_prices_preserves_twse_change_marker_in_note(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return {
                "stat": "OK",
                "data": [
                    [
                        "114/06/12",
                        "28,661,875",
                        "30,064,888,046",
                        "1,055.00",
                        "1,060.00",
                        "1,045.00",
                        "1,045.00",
                        "X0.00",
                        "40,293",
                        "",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json)
        prices = client.fetch_daily_prices_for_month("2330", date(2025, 6, 1))

        self.assertEqual(prices[0].change, 0.0)
        self.assertEqual(prices[0].note, "change_marker=X")

    def test_fetch_daily_prices_skips_one_failed_month(self) -> None:
        def fake_fetch_json(url: str) -> object:
            if "date=20250801" in url:
                raise TwseError("Cannot fetch TWSE url")
            return {
                "stat": "OK",
                "data": [
                    [
                        "114/09/01",
                        "1,000",
                        "40,000",
                        "40.00",
                        "41.00",
                        "39.50",
                        "40.50",
                        "+0.50",
                        "100",
                        "",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json, request_interval=0)
        prices = client.fetch_daily_prices("2303", date(2025, 8, 1), date(2025, 9, 30))

        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].date, date(2025, 9, 1))
        self.assertEqual(len(client.last_warnings), 1)
        self.assertIn("2025-08", client.last_warnings[0])

    def test_fetch_daily_prices_retries_failed_month(self) -> None:
        attempts: dict[str, int] = {}

        def fake_fetch_json(url: str) -> object:
            key = "202508" if "date=20250801" in url else "202509"
            attempts[key] = attempts.get(key, 0) + 1
            if key == "202508" and attempts[key] == 1:
                raise TwseError("temporary TWSE failure")
            roc_date = "114/08/01" if key == "202508" else "114/09/01"
            return {
                "stat": "OK",
                "data": [
                    [
                        roc_date,
                        "1,000",
                        "40,000",
                        "40.00",
                        "41.00",
                        "39.50",
                        "40.50",
                        "+0.50",
                        "100",
                        "",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json, request_interval=0)
        prices = client.fetch_daily_prices("2303", date(2025, 8, 1), date(2025, 9, 30))

        self.assertEqual([item.date for item in prices], [date(2025, 8, 1), date(2025, 9, 1)])
        self.assertEqual(client.last_warnings, [])
        self.assertEqual(attempts["202508"], 2)

    def test_fetch_daily_prices_prioritizes_newer_months(self) -> None:
        seen_dates: list[str] = []

        def fake_fetch_json(url: str) -> object:
            query_date = url.split("date=", 1)[1].split("&", 1)[0]
            seen_dates.append(query_date)
            roc_date = "114/09/01" if query_date == "20250901" else "114/08/01"
            return {
                "stat": "OK",
                "data": [
                    [
                        roc_date,
                        "1,000",
                        "40,000",
                        "40.00",
                        "41.00",
                        "39.50",
                        "40.50",
                        "+0.50",
                        "100",
                        "",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json, request_interval=0)
        prices = client.fetch_daily_prices("2303", date(2025, 8, 1), date(2025, 9, 30))

        self.assertEqual(seen_dates, ["20250901", "20250801"])
        self.assertEqual([item.date for item in prices], [date(2025, 8, 1), date(2025, 9, 1)])

    def test_fetch_listed_profiles_maps_company_profile_fields(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("t187ap03_L", url)
            return [
                {
                    "出表日期": "1150611",
                    "公司代號": "2330",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                    "公司簡稱": "台積電",
                    "產業別": "24",
                    "上市日期": "19940905",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        profiles = client.fetch_listed_profiles()

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].stock_id, "2330")
        self.assertEqual(profiles[0].short_name, "台積電")
        self.assertEqual(profiles[0].listed_date, date(1994, 9, 5))
        self.assertEqual(profiles[0].source_updated_at, date(2026, 6, 11))

    def test_fetch_dividend_records_maps_cash_and_stock_dividends(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return [
                {
                    "出表日期": "1150611",
                    "公司代號": "2330",
                    "決議（擬議）進度": "董事會決議",
                    "股利年度": "115",
                    "股利所屬年(季)度": "第1季",
                    "董事會（擬議）股利分派日": "1150512",
                    "股東會日期": "",
                    "股東配發-盈餘分配之現金股利(元/股)": "7.00000000",
                    "股東配發-法定盈餘公積發放之現金(元/股)": "0.0",
                    "股東配發-資本公積發放之現金(元/股)": "0.0",
                    "股東配發-盈餘轉增資配股(元/股)": "0.0",
                    "股東配發-法定盈餘公積轉增資配股(元/股)": "0.0",
                    "股東配發-資本公積轉增資配股(元/股)": "0.0",
                    "備註": "無。",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        records = client.fetch_dividend_records("2330")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].year, 115)
        self.assertEqual(records[0].cash_dividend, 7.0)
        self.assertEqual(records[0].board_date, date(2026, 5, 12))

    def test_fetch_dividend_records_uses_distribution_year_for_annual_dividend(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return [
                {
                    "出表日期": "1150614",
                    "公司代號": "2303",
                    "決議（擬議）進度": "股東會確認",
                    "股利年度": "114",
                    "股利所屬年(季)度": "年度",
                    "董事會（擬議）股利分派日": "1150225",
                    "股東會日期": "1150527",
                    "股東配發-盈餘分配之現金股利(元/股)": "2.60000000",
                    "股東配發-法定盈餘公積發放之現金(元/股)": "0.0",
                    "股東配發-資本公積發放之現金(元/股)": "0.0",
                    "股東配發-盈餘轉增資配股(元/股)": "0.0",
                    "股東配發-法定盈餘公積轉增資配股(元/股)": "0.0",
                    "股東配發-資本公積轉增資配股(元/股)": "0.0",
                    "備註": "",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        records = client.fetch_dividend_records("2303")

        self.assertEqual(records[0].year, 115)
        self.assertEqual(records[0].cash_dividend, 2.6)

    def test_fetch_dividend_records_notes_distribution_components(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return [
                {
                    "出表日期": "1150614",
                    "公司代號": "2303",
                    "決議（擬議）進度": "股東會確認",
                    "股利年度": "114",
                    "股利所屬年(季)度": "年度",
                    "董事會（擬議）股利分派日": "1150225",
                    "股東會日期": "1150527",
                    "股東配發-盈餘分配之現金股利(元/股)": "2.60000000",
                    "股東配發-法定盈餘公積發放之現金(元/股)": "0.10000000",
                    "股東配發-資本公積發放之現金(元/股)": "0.20000000",
                    "股東配發-盈餘轉增資配股(元/股)": "0.30000000",
                    "股東配發-法定盈餘公積轉增資配股(元/股)": "0.00000000",
                    "股東配發-資本公積轉增資配股(元/股)": "0.05000000",
                    "備註": "無。",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        records = client.fetch_dividend_records("2303")

        self.assertAlmostEqual(records[0].cash_dividend, 2.9)
        self.assertAlmostEqual(records[0].stock_dividend, 0.35)
        self.assertIn("現金股利口徑", records[0].note)
        self.assertIn("法定盈餘公積現金 0.1", records[0].note)
        self.assertIn("資本公積現金 0.2", records[0].note)
        self.assertIn("股票股利口徑", records[0].note)
        self.assertNotIn("無。", records[0].note)

    def test_fetch_historical_dividend_records_maps_ex_dividend_cash(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("TWT49U", url)
            return {
                "stat": "OK",
                "data": [
                    [
                        "114年06月24日",
                        "2303",
                        "聯電",
                        "47.00",
                        "44.14",
                        "2.850164",
                        "息",
                    ],
                    [
                        "114年07月01日",
                        "2317",
                        "鴻海",
                        "100.00",
                        "95.00",
                        "5.000000",
                        "息",
                    ],
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json, request_interval=0)
        records = client.fetch_historical_dividend_records(
            "2303",
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].year, 114)
        self.assertAlmostEqual(records[0].cash_dividend, 2.850164)
        self.assertEqual(records[0].source, "TWSE_TWT49U")
        self.assertIn("權值不是每股股票股利", records[0].note)

    def test_fetch_historical_dividend_records_skips_failed_year(self) -> None:
        def fake_fetch_json(url: str) -> object:
            if "startDate=20240101" in url:
                raise TwseError("temporary redirect")
            return {
                "stat": "OK",
                "data": [
                    [
                        "114年06月24日",
                        "2303",
                        "聯電",
                        "47.00",
                        "44.14",
                        "2.850164",
                        "息",
                    ]
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json, request_interval=0)
        records = client.fetch_historical_dividend_records(
            "2303",
            date(2024, 1, 1),
            date(2025, 12, 31),
        )

        self.assertEqual(len(records), 1)
        self.assertIn("2024", client.last_warnings[0])

    def test_fetch_market_valuation_maps_bwi_payload(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return [
                {
                    "Date": "1150611",
                    "Code": "2330",
                    "Name": "台積電",
                    "PEratio": "30.25",
                    "DividendYield": "0.98",
                    "PBratio": "9.90",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        valuation = client.fetch_market_valuation("2330")

        self.assertIsNotNone(valuation)
        self.assertEqual(valuation.date, date(2026, 6, 11))  # type: ignore[union-attr]
        self.assertEqual(valuation.pe_ratio, 30.25)  # type: ignore[union-attr]

    def test_shared_metadata_cache_reuses_payload_across_clients(self) -> None:
        calls: list[str] = []

        def fake_fetch_json(url: str) -> object:
            calls.append(url)
            return [
                {
                    "Date": "1150611",
                    "Code": "2330",
                    "Name": "台積電",
                    "PEratio": "30.25",
                    "DividendYield": "0.98",
                    "PBratio": "9.90",
                }
            ]

        TwseClient.clear_shared_cache()
        try:
            first = TwseClient(fetch_json=fake_fetch_json)
            second = TwseClient(fetch_json=fake_fetch_json)
            first._cache_enabled = True
            second._cache_enabled = True

            self.assertEqual(first.fetch_market_valuation("2330").pe_ratio, 30.25)  # type: ignore[union-attr]
            self.assertEqual(second.fetch_market_valuation("2330").pb_ratio, 9.9)  # type: ignore[union-attr]
        finally:
            TwseClient.clear_shared_cache()

        self.assertEqual(len(calls), 1)

    def test_fetch_monthly_revenue_maps_twse_payload(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("t187ap05_L", url)
            return [
                {
                    "出表日期": "1150611",
                    "資料年月": "11505",
                    "公司代號": "2330",
                    "公司名稱": "台積電",
                    "產業別": "半導體業",
                    "營業收入-當月營收": "416975163",
                    "營業收入-上月營收": "410725118",
                    "營業收入-去年當月營收": "320515951",
                    "營業收入-上月比較增減(%)": "1.5217",
                    "營業收入-去年同月增減(%)": "30.095",
                    "累計營業收入-當月累計營收": "1961803721",
                    "累計營業收入-去年累計營收": "1509336555",
                    "累計營業收入-前期比較增減(%)": "29.9779",
                    "備註": "-",
                }
            ]

        client = TwseClient(fetch_json=fake_fetch_json)
        revenue = client.fetch_monthly_revenue("2330")

        self.assertIsNotNone(revenue)
        self.assertEqual(revenue.year_month, "2026-05")  # type: ignore[union-attr]
        self.assertEqual(revenue.current_month_revenue, 416975163)  # type: ignore[union-attr]
        self.assertEqual(revenue.yoy_percent, 30.095)  # type: ignore[union-attr]
        self.assertEqual(revenue.source_updated_at, date(2026, 6, 11))  # type: ignore[union-attr]

    def test_fetch_financial_statement_combines_income_and_balance_rows(self) -> None:
        def fake_fetch_json(url: str) -> object:
            if "t187ap06_L_ci" in url:
                return [
                    {
                        "出表日期": "1150612",
                        "年度": "115",
                        "季別": "1",
                        "公司代號": "2330",
                        "公司名稱": "台積電",
                        "營業收入": "1134103440.00",
                        "營業毛利（毛損）": "751295421.00",
                        "營業利益（損失）": "658966142.00",
                        "營業外收入及支出": "28833545.00",
                        "稅前淨利（淨損）": "687799687.00",
                        "本期淨利（淨損）": "572801304.00",
                        "淨利（淨損）歸屬於母公司業主": "572479752.00",
                        "基本每股盈餘（元）": "22.08",
                    }
                ]
            if "t187ap07_L_ci" in url:
                return [
                    {
                        "出表日期": "1150612",
                        "年度": "115",
                        "季別": "1",
                        "公司代號": "2330",
                        "公司名稱": "台積電",
                        "資產總額": "8660949685.00",
                        "負債總額": "2728560764.00",
                        "歸屬於母公司業主之權益合計": "5890960252.00",
                        "權益總額": "5932388921.00",
                        "每股參考淨值": "227.17",
                    }
                ]
            return []

        client = TwseClient(fetch_json=fake_fetch_json)
        statement = client.fetch_financial_statement("2330")

        self.assertIsNotNone(statement)
        self.assertEqual(statement.year, 2026)  # type: ignore[union-attr]
        self.assertEqual(statement.quarter, 1)  # type: ignore[union-attr]
        self.assertEqual(statement.eps, 22.08)  # type: ignore[union-attr]
        self.assertEqual(statement.parent_equity, 5890960252)  # type: ignore[union-attr]
        self.assertEqual(statement.source_updated_at, date(2026, 6, 12))  # type: ignore[union-attr]

    def test_fetch_intraday_quote_maps_mis_payload(self) -> None:
        def fake_fetch_json(url: str) -> object:
            self.assertIn("getStockInfo", url)
            return {
                "rtcode": "0000",
                "userDelay": 5000,
                "msgArray": [
                    {
                        "c": "2330",
                        "n": "台積電",
                        "nf": "台灣積體電路製造股份有限公司",
                        "d": "20260612",
                        "t": "11:29:00",
                        "z": "2305.0000",
                        "y": "2250.0000",
                        "o": "2325.0000",
                        "h": "2325.0000",
                        "l": "2290.0000",
                        "v": "12003",
                        "a": "2310.0000_2315.0000_",
                        "b": "2305.0000_2300.0000_",
                    }
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json)
        quote = client.fetch_intraday_quote("2330")

        self.assertIsNotNone(quote)
        self.assertEqual(quote.stock_id, "2330")  # type: ignore[union-attr]
        self.assertEqual(quote.current_price, 2305.0)  # type: ignore[union-attr]
        self.assertEqual(quote.previous_close, 2250.0)  # type: ignore[union-attr]
        self.assertEqual(quote.best_bid_price, 2305.0)  # type: ignore[union-attr]
        self.assertEqual(quote.best_ask_price, 2310.0)  # type: ignore[union-attr]

    def test_fetch_intraday_quote_allows_missing_trade_price(self) -> None:
        def fake_fetch_json(url: str) -> object:
            return {
                "rtcode": "0000",
                "msgArray": [
                    {
                        "c": "2330",
                        "d": "20260612",
                        "t": "11:29:00",
                        "z": "-",
                        "y": "2250.0000",
                        "a": "2300.0000_",
                        "b": "2295.0000_",
                    }
                ],
            }

        client = TwseClient(fetch_json=fake_fetch_json)
        quote = client.fetch_intraday_quote("2330")

        self.assertIsNotNone(quote)
        self.assertIsNone(quote.current_price)  # type: ignore[union-attr]
        self.assertEqual(quote.best_bid_price, 2295.0)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
