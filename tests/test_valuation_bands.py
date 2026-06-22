import unittest
import math
from datetime import date, timedelta

from app.analyze.valuation_bands import (
    compute_valuation_bands,
    position_phrase,
)


def _financials():
    rows = []
    for year in range(2020, 2026):
        for quarter in range(1, 5):
            qend = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
            rows.append(
                {
                    "year": year,
                    "quarter": quarter,
                    "eps": 1.0,  # TTM = 4.0（穩定）
                    "book_value_per_share": 20.0,
                    "source_updated_at": date(year, qend[0], qend[1]) + timedelta(days=50),
                }
            )
    return rows


def _prices():
    rows = []
    start = date(2025, 1, 1)
    closes = []
    # 產生 200 個交易日，收盤在 80~120 間規律變動
    for i in range(200):
        closes.append(80 + (i % 41))  # 80..120
    d = start
    idx = 0
    while idx < len(closes):
        if d.weekday() < 5:
            rows.append({"date": d, "close": float(closes[idx])})
            idx += 1
        d += timedelta(days=1)
    return rows


def _golden_financials():
    return [
        {
            "year": 2024,
            "quarter": quarter,
            "eps": 1.0,
            "book_value_per_share": 20.0,
            "source_updated_at": date(2024, 12, 31),
        }
        for quarter in range(1, 5)
    ]


def _golden_prices():
    start = date(2025, 1, 1)
    return [
        {
            "date": start + timedelta(days=index),
            "open": float(index + 1),
            "high": float(index + 1),
            "low": float(index + 1),
            "close": float(index + 1),
            "volume": 1000,
        }
        for index in range(60)
    ]


class ValuationBandsTest(unittest.TestCase):
    def setUp(self):
        self.result = compute_valuation_bands(
            _prices(), _financials(), today=date(2025, 12, 31), years=5
        )

    def test_pe_band_available_and_ordered(self):
        pe = self.result["pe"]
        self.assertTrue(pe["available"], pe)
        self.assertGreaterEqual(pe["sample_size"], 60)
        self.assertLessEqual(pe["p20"], pe["p50"])
        self.assertLessEqual(pe["p50"], pe["p80"])
        # TTM EPS = 4，PE = close/4，收盤 80~120 -> PE 20~30
        self.assertGreaterEqual(pe["low"], 19.9)
        self.assertLessEqual(pe["high"], 30.1)

    def test_pb_band_available(self):
        pb = self.result["pb"]
        self.assertTrue(pb["available"], pb)
        # BVPS = 20，PB = close/20，收盤 80~120 -> PB 4~6
        self.assertGreaterEqual(pb["low"], 3.9)
        self.assertLessEqual(pb["high"], 6.1)

    def test_current_percentile_in_range(self):
        pe = self.result["pe"]
        self.assertIsNotNone(pe["current_percentile"])
        self.assertGreaterEqual(pe["current_percentile"], 0)
        self.assertLessEqual(pe["current_percentile"], 100)

    def test_insufficient_data_marks_unavailable(self):
        result = compute_valuation_bands(_prices()[:10], _financials(), today=date(2025, 12, 31))
        self.assertFalse(result["pe"]["available"])

    def test_position_phrase_is_neutral(self):
        for pct in (5, 50, 95, None):
            phrase = position_phrase(pct)
            self.assertIsInstance(phrase, str)
            for forbidden in ("便宜", "昂貴", "該買", "會漲", "會跌"):
                self.assertNotIn(forbidden, phrase)

    def test_fixed_percentiles_and_current_position(self):
        result = compute_valuation_bands(
            _golden_prices(),
            _golden_financials(),
            today=date(2025, 3, 31),
            years=1,
        )

        pe = result["pe"]
        pb = result["pb"]
        self.assertTrue(pe["available"], pe)
        self.assertEqual(pe["sample_size"], 60)
        self.assertEqual(pe["low"], 0.25)
        self.assertEqual(pe["high"], 15.0)
        self.assertEqual(pe["current"], 15.0)
        self.assertEqual(pe["current_percentile"], 100)
        self.assertEqual(pe["p20"], 3.2)
        self.assertEqual(pe["p50"], 7.62)
        self.assertEqual(pe["p80"], 12.05)
        self.assertEqual(pb["p50"], 1.52)

    def test_bad_price_rows_do_not_pollute_bands(self):
        clean = compute_valuation_bands(
            _golden_prices(),
            _golden_financials(),
            today=date(2025, 3, 31),
            years=1,
        )
        dirty_prices = _golden_prices()[:10] + [
            {"date": date(2025, 1, 12), "close": 0},
            {"date": date(2025, 1, 13), "close": math.nan},
            {
                "date": date(2025, 1, 14),
                "open": 500,
                "high": 500,
                "low": 500,
                "close": 500,
                "volume": 0,
            },
        ] + _golden_prices()[10:]

        dirty = compute_valuation_bands(
            dirty_prices,
            _golden_financials(),
            today=date(2025, 3, 31),
            years=1,
        )

        self.assertEqual(dirty["pe"]["sample_size"], clean["pe"]["sample_size"])
        self.assertEqual(dirty["pe"]["current"], clean["pe"]["current"])
        self.assertEqual(dirty["pe"]["p50"], clean["pe"]["p50"])


if __name__ == "__main__":
    unittest.main()
