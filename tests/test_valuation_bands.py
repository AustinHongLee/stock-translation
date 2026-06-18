import unittest
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


if __name__ == "__main__":
    unittest.main()
