from __future__ import annotations

import unittest
from datetime import date

from app.models import DailyPrice, StockProfile
from app.sync.market_router import MarketRoutedClient, store_market_lookup


class _RecorderClient:
    """記錄呼叫的假 client；fetch_daily_prices 刻意「不支援 on_month」測相容層。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls: list[tuple[str, str]] = []
        self.last_warnings: list[str] = []

    def fetch_daily_prices(self, stock_id: str, start_date: date, end_date: date) -> list[DailyPrice]:
        self.calls.append(("daily", stock_id))
        self.last_warnings = [f"{self.tag}-warning"]
        return [DailyPrice(stock_id, end_date, 10, 11, 9, 10, 1000)]

    def fetch_profile(self, stock_id: str) -> StockProfile | None:
        self.calls.append(("profile", stock_id))
        if self.tag == "twse" and stock_id.startswith("53"):
            return None  # 模擬 TWSE 查無上櫃股
        return StockProfile(
            stock_id=stock_id,
            name=f"{self.tag}-{stock_id}",
            short_name=self.tag,
            market="TWSE" if self.tag == "twse" else "TPEX",
        )

    def fetch_market_valuation(self, stock_id: str):
        self.calls.append(("valuation", stock_id))
        self.last_warnings = []
        return None

    def fetch_monthly_revenue(self, stock_id: str):
        self.calls.append(("revenue", stock_id))
        self.last_warnings = []
        return None

    def fetch_financial_statement(self, stock_id: str):
        self.calls.append(("financial", stock_id))
        return None

    def fetch_dividend_records(self, stock_id: str) -> list:
        self.calls.append(("dividends", stock_id))
        return []

    def fetch_historical_dividend_records(self, stock_id: str, start_date: date, end_date: date) -> list:
        self.calls.append(("hist_dividends", stock_id))
        return []

    def fetch_institutional_trades(self, stock_id: str, start_date: date, end_date: date, **kwargs) -> list:
        self.calls.append(("institutional", stock_id))
        return []

    def throttle_factor(self) -> float:
        return 2.0 if self.tag == "twse" else 8.0


def _router(markets: dict[str, str]) -> tuple[MarketRoutedClient, _RecorderClient, _RecorderClient]:
    twse = _RecorderClient("twse")
    tpex = _RecorderClient("tpex")
    client = MarketRoutedClient(twse, tpex, market_lookup=markets.get)
    return client, twse, tpex


class MarketRoutingTests(unittest.TestCase):
    def test_tpex_stock_routes_to_tpex_only(self) -> None:
        client, twse, tpex = _router({"5347": "TPEX"})
        client.fetch_daily_prices("5347", date(2026, 7, 1), date(2026, 7, 31))
        client.fetch_monthly_revenue("5347")
        self.assertEqual(twse.calls, [])
        self.assertEqual([c[0] for c in tpex.calls], ["daily", "revenue"])
        self.assertEqual(client.last_warnings, [])  # revenue 呼叫後採用 tpex warnings（空）

    def test_twse_and_unknown_stock_routes_to_twse(self) -> None:
        client, twse, tpex = _router({"2330": "TWSE"})
        client.fetch_daily_prices("2330", date(2026, 7, 1), date(2026, 7, 31))
        client.fetch_daily_prices("9999", date(2026, 7, 1), date(2026, 7, 31))  # 未知 → 預設 TWSE
        self.assertEqual([c for c in twse.calls if c[0] == "daily"], [("daily", "2330"), ("daily", "9999")])
        self.assertEqual(tpex.calls, [])
        self.assertEqual(client.last_warnings, ["twse-warning"])

    def test_unknown_profile_probes_twse_then_tpex(self) -> None:
        client, twse, tpex = _router({})
        profile = client.fetch_profile("5347")  # TWSE 查無 → TPEX 探測
        assert profile is not None
        self.assertEqual(profile.market, "TPEX")
        self.assertIn(("profile", "5347"), twse.calls)
        self.assertIn(("profile", "5347"), tpex.calls)

    def test_tpex_dividends_and_institutional_return_empty_without_calls(self) -> None:
        client, twse, tpex = _router({"5347": "TPEX"})
        self.assertEqual(client.fetch_dividend_records("5347"), [])
        self.assertEqual(
            client.fetch_historical_dividend_records("5347", date(2025, 1, 1), date(2026, 1, 1)),
            [],
        )
        self.assertEqual(
            client.fetch_institutional_trades("5347", date(2026, 7, 1), date(2026, 7, 31)),
            [],
        )
        self.assertEqual(twse.calls, [])
        self.assertEqual(tpex.calls, [])

    def test_on_month_falls_back_to_single_batch_for_legacy_clients(self) -> None:
        client, _twse, _tpex = _router({})
        batches: list[list[DailyPrice]] = []
        prices = client.fetch_daily_prices(
            "2330", date(2026, 7, 1), date(2026, 7, 31), on_month=batches.append
        )
        self.assertEqual(len(batches), 1)  # 子 client 不支援 on_month → 整批一次回呼
        self.assertEqual(batches[0], prices)

    def test_throttle_factor_takes_max(self) -> None:
        client, _twse, _tpex = _router({})
        self.assertEqual(client.throttle_factor(), 8.0)

    def test_store_market_lookup_reads_profile(self) -> None:
        class FakeStore:
            def get_profile(self, stock_id: str):
                if stock_id == "5347":
                    return StockProfile(stock_id="5347", name="x", short_name="x", market="TPEX")
                return None

        lookup = store_market_lookup(FakeStore())
        self.assertEqual(lookup("5347"), "TPEX")
        self.assertIsNone(lookup("2330"))


if __name__ == "__main__":
    unittest.main()
