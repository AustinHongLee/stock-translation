import unittest
import urllib.parse as up
from datetime import date

from app.models import InstitutionalTrade
from app.sync.twse import TwseClient


def _row(code, foreign, trust, dealer, total):
    """仿 T86 ALLBUT0999 欄位：0代號 1名稱 4外資 10投信 11自營 18三大法人。"""
    r = [""] * 19
    r[0] = code
    r[1] = code + " 名"
    r[4] = foreign
    r[10] = trust
    r[11] = dealer
    r[18] = total
    return r


class T86ParseTest(unittest.TestCase):
    def test_extracts_correct_columns_and_signs(self):
        payload = {
            "stat": "OK",
            "data": [
                _row("2317", "1,000", "2,000", "3,000", "6,000"),
                _row("2330", "20,652,968", "-23,164", "-2,686,113", "262,271"),
            ],
        }
        client = TwseClient(fetch_json=lambda url: payload, request_interval=0)
        t = client.fetch_institutional_trade_for_stock_on("2330", date(2025, 6, 13))
        self.assertIsInstance(t, InstitutionalTrade)
        self.assertEqual(t.foreign_net, 20652968)
        self.assertEqual(t.trust_net, -23164)
        self.assertEqual(t.dealer_net, -2686113)
        self.assertEqual(t.total_net, 262271)
        self.assertEqual(t.date, date(2025, 6, 13))

    def test_non_trading_day_returns_none(self):
        client = TwseClient(
            fetch_json=lambda url: {"stat": "很抱歉，沒有符合條件的資料!", "total": 0},
            request_interval=0,
        )
        self.assertIsNone(client.fetch_institutional_trade_for_stock_on("2330", date(2025, 1, 1)))

    def test_window_skips_weekends_and_sorts_oldest_first(self):
        def fake(url):
            d = up.parse_qs(up.urlparse(url).query)["date"][0]
            mapping = {"20250613": "300", "20250612": "-100"}
            if d in mapping:
                return {"stat": "OK", "data": [_row("2330", mapping[d], "0", "0", mapping[d])]}
            return {"stat": "no data", "total": 0}

        client = TwseClient(fetch_json=fake, request_interval=0)
        trades = client.fetch_institutional_trades("2330", date(2025, 6, 1), date(2025, 6, 16), max_days=20)
        self.assertEqual([t.date for t in trades], [date(2025, 6, 12), date(2025, 6, 13)])
        self.assertEqual([t.total_net for t in trades], [-100, 300])

    def test_window_tolerates_long_empty_stretch_before_trade(self):
        def fake(url):
            d = up.parse_qs(up.urlparse(url).query)["date"][0]
            if d == "20250613":
                return {"stat": "OK", "data": [_row("2330", "300", "0", "0", "300")]}
            return {"stat": "no data", "total": 0}

        client = TwseClient(fetch_json=fake, request_interval=0)
        trades = client.fetch_institutional_trades("2330", date(2025, 6, 1), date(2025, 6, 30), max_days=20)

        self.assertEqual([t.date for t in trades], [date(2025, 6, 13)])

    def test_window_skips_official_twse_holidays(self):
        requested_dates: list[str] = []

        def fake(url):
            d = up.parse_qs(up.urlparse(url).query)["date"][0]
            requested_dates.append(d)
            if d == "20260211":
                return {"stat": "OK", "data": [_row("2330", "300", "0", "0", "300")]}
            return {"stat": "no data", "total": 0}

        client = TwseClient(fetch_json=fake, request_interval=0)
        trades = client.fetch_institutional_trades("2330", date(2026, 2, 11), date(2026, 2, 23))

        self.assertEqual([t.date for t in trades], [date(2026, 2, 11)])
        self.assertEqual(requested_dates, ["20260223", "20260211"])


if __name__ == "__main__":
    unittest.main()
