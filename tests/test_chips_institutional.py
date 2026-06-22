import unittest
from datetime import date, timedelta

from app.chips import build_institutional_summary
from app.chips.institutional import consecutive_sell_days
from app.models import InstitutionalTrade
from app.news.classifier import contains_forbidden


def _series(triples):
    """triples 由舊到新：(外資, 投信, 自營) 淨買賣超；total 自動加總。"""
    base = date(2026, 6, 16)
    n = len(triples)
    out = []
    for i, (f, t, d) in enumerate(triples):
        out.append(
            InstitutionalTrade("2330", base - timedelta(days=(n - 1 - i)), f, t, d, f + t + d)
        )
    return out


class ChipsSummaryTest(unittest.TestCase):
    def test_empty(self):
        s = build_institutional_summary([])
        self.assertFalse(s["available"])
        self.assertEqual(s["level"], "無")

    def test_consecutive_sell_escalates_to_warning(self):
        s = build_institutional_summary(_series([(1000, 100, 10)] * 2 + [(-50000, -3000, -1000)] * 5))
        self.assertTrue(s["available"])
        self.assertEqual(s["consecutive_total_sell_days"], 5)
        self.assertEqual(s["consecutive_foreign_sell_days"], 5)
        self.assertEqual(s["level"], "警戒")

    def test_buy_side_is_calm(self):
        s = build_institutional_summary(_series([(30000, 5000, 100)] * 6))
        self.assertEqual(s["level"], "無")
        self.assertEqual(s["consecutive_total_sell_days"], 0)

    def test_latest_total_sell_only_is_low(self):
        s = build_institutional_summary(_series([(1000, 1, 1)] * 5 + [(-200, 50, 10)]))
        self.assertEqual(s["consecutive_total_sell_days"], 1)
        self.assertFalse(s["all_three_sell"])
        self.assertEqual(s["level"], "留意")

    def test_sum20_and_latest_fields(self):
        s = build_institutional_summary(_series([(100, 0, 0), (200, 0, 0), (-50, 0, 0)]))
        self.assertEqual(s["latest"]["total_net"], -50)
        self.assertEqual(s["sum_20"]["total_net"], 250)
        self.assertEqual(s["sum_20"]["foreign_net"], 250)
        self.assertEqual(len(s["trend"]), 3)

    def test_share_inputs_are_reported_as_lots(self):
        s = build_institutional_summary(_series([(-123456, 0, 0)]))
        text = " ".join([s["headline"], *s["reasons"], *s["analysis"]])
        self.assertIn("123 張", text)
        self.assertEqual(s["latest"]["foreign_net"], -123456)

    def test_no_forbidden_words(self):
        s = build_institutional_summary(_series([(-50000, -3000, -1000)] * 5))
        blob = " ".join(s["reasons"] + [s["headline"], s["disclaimer"]] + list(s["proxy_notes"].values()))
        self.assertEqual(contains_forbidden(blob), [])

    def test_consecutive_helper(self):
        self.assertEqual(consecutive_sell_days([1, 1, 1, -1]), 3)
        self.assertEqual(consecutive_sell_days([-1, 1]), 0)


    def test_analysis_present_and_clean(self):
        s = build_institutional_summary(_series([(1000, 100, 10)] * 15 + [(-80000, 30000, -2000)] * 5))
        self.assertTrue(s["analysis"])
        self.assertIn("analysis_note", s)
        blob = " ".join(s["analysis"] + [s["analysis_note"]])
        self.assertEqual(contains_forbidden(blob), [])


if __name__ == "__main__":
    unittest.main()
