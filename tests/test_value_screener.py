from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.models import DailyPrice, DividendRecord, StockProfile
from app.screener.value import build_value_screener_payload, load_value_screener


class ValueScreenerTests(unittest.TestCase):
    def test_load_value_screener_backfills_snapshot_rankings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "value_screener.json"
            path.write_text(
                json.dumps(
                    {
                        "summary": {},
                        "items": [
                            {
                                "stock_id": "2330",
                                "short_name": "台積電",
                                "price_date": "2026-06-22",
                                "current_price": 2440,
                                "previous_close": 2400,
                                "open_price": 2420,
                                "high_price": 2460,
                                "low_price": 2390,
                                "volume": 1000,
                                "trade_value": 2_440_000,
                                "day_change_percent": 1.6,
                            },
                            {
                                "stock_id": "2303",
                                "short_name": "聯電",
                                "price_date": "2026-06-22",
                                "current_price": 50,
                                "previous_close": 52,
                                "open_price": 51,
                                "high_price": 53,
                                "low_price": 49,
                                "volume": 2000,
                                "trade_value": 100_000,
                                "day_change_percent": -3.8,
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = load_value_screener(path)

        self.assertEqual(payload["summary"]["volume_leaders_rows"], 2)  # type: ignore[index]
        self.assertEqual(payload["volume_leaders"][0]["stock_id"], "2303")  # type: ignore[index]
        self.assertEqual(payload["turnover_leaders"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(payload["gap_up"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(payload["gap_down"][0]["stock_id"], "2303")  # type: ignore[index]
        self.assertAlmostEqual(payload["items"][0]["amplitude_percent"], 2.9166666666666665)  # type: ignore[index]

    def test_build_value_screener_payload_calculates_difference(self) -> None:
        payload = build_value_screener_payload(
            profiles=[
                StockProfile(stock_id="2303", name="聯華電子股份有限公司", short_name="聯電"),
                StockProfile(stock_id="2330", name="台積電", short_name="台積電"),
                StockProfile(
                    stock_id="7722",
                    name="連加網路商業股份有限公司",
                    short_name="LINEPAY",
                    listed_date=date(2024, 12, 5),
                ),
            ],
            prices=[
                DailyPrice(
                    stock_id="2303",
                    date=date(2026, 6, 15),
                    open=140,
                    high=142,
                    low=130,
                    close=48,
                    volume=100,
                    trade_value=4_800_000,
                    transaction_count=80,
                    change=1.2,
                ),
                DailyPrice(
                    stock_id="2330",
                    date=date(2026, 6, 15),
                    open=2300,
                    high=2400,
                    low=2200,
                    close=2375,
                    volume=200,
                    trade_value=475_000_000,
                    transaction_count=160,
                    change=-20,
                ),
                DailyPrice(
                    stock_id="7722",
                    date=date(2026, 6, 15),
                    open=327,
                    high=337.5,
                    low=321,
                    close=327,
                    volume=50,
                    trade_value=16_350_000,
                    transaction_count=40,
                    change=0,
                ),
            ],
            dividends=[
                DividendRecord("2303", 115, "年度", "股東會確認", None, None, 3.01, 0),
                DividendRecord("2303", 114, "年度", "股東會確認", None, None, 3.01, 0),
                DividendRecord("2303", 113, "年度", "股東會確認", None, None, 3.01, 0),
                DividendRecord("2303", 112, "年度", "股東會確認", None, None, 3.01, 0),
                DividendRecord("2303", 111, "年度", "股東會確認", None, None, 3.01, 0),
                DividendRecord("2330", 115, "年度", "股東會確認", None, None, 15.1, 0),
                DividendRecord("2330", 114, "年度", "股東會確認", None, None, 15.1, 0),
                DividendRecord("2330", 113, "年度", "股東會確認", None, None, 15.1, 0),
                DividendRecord("2330", 112, "年度", "股東會確認", None, None, 15.1, 0),
                DividendRecord("2330", 111, "年度", "股東會確認", None, None, 15.1, 0),
                DividendRecord("7722", 115, "除息 06/15", "除息", None, None, 1.5, 0, source="TWSE_TWT49U"),
                DividendRecord("7722", 114, "除息 09/04", "除息", None, None, 1.5, 0, source="TWSE_TWT49U"),
            ],
            generated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            source_start_date=date(2021, 1, 1),
            source_end_date=date(2026, 6, 15),
        )

        items = payload["items"]  # type: ignore[index]
        first = items[0]  # type: ignore[index]
        by_id = {item["stock_id"]: item for item in items}  # type: ignore[index]
        umc = by_id["2303"]

        self.assertEqual(first["stock_id"], "2303")
        self.assertAlmostEqual(umc["average_cash_dividend"], 3.01)
        self.assertAlmostEqual(umc["cheap_price"], 48.16)
        self.assertAlmostEqual(umc["difference"], -0.16)
        self.assertLess(umc["difference_percent"], 0)
        self.assertAlmostEqual(umc["previous_close"], 46.8)
        self.assertAlmostEqual(umc["day_change_percent"], 2.564102564102564)
        self.assertAlmostEqual(umc["opening_gap_percent"], 199.14529914529913)
        self.assertAlmostEqual(umc["amplitude_percent"], 25.64102564102564)
        self.assertEqual(umc["trade_value"], 4_800_000)
        self.assertEqual(umc["transaction_count"], 80)
        self.assertAlmostEqual(umc["current_yield_percent"], 6.270833333333334)
        self.assertEqual(umc["confidence"], "high")
        self.assertEqual(by_id["7722"]["confidence"], "low")
        self.assertIn("殖利率低於 1%", " ".join(by_id["7722"]["confidence_notes"]))
        self.assertEqual(payload["summary"]["below_cheap_rows"], 1)  # type: ignore[index]
        self.assertEqual(payload["summary"]["gainers_rows"], 1)  # type: ignore[index]
        self.assertEqual(payload["summary"]["losers_rows"], 1)  # type: ignore[index]
        self.assertEqual(payload["summary"]["turnover_leaders_rows"], 3)  # type: ignore[index]
        self.assertEqual(payload["summary"]["volume_leaders_rows"], 3)  # type: ignore[index]
        self.assertEqual(payload["summary"]["amplitude_leaders_rows"], 3)  # type: ignore[index]
        self.assertEqual(payload["turnover_leaders"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(payload["volume_leaders"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(payload["gap_up"][0]["stock_id"], "2303")  # type: ignore[index]
        self.assertEqual(payload["amplitude_leaders"][0]["stock_id"], "2303")  # type: ignore[index]
        self.assertEqual(payload["summary"]["low_confidence_rows"], 2)  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
