import unittest
from datetime import date

from app.news.classifier import contains_forbidden
from app.news.risk_matrix import build_risk_summary, rolling_risk, score_news
from app.news.service import build_news_payload


class RiskMatrixTest(unittest.TestCase):
    # ---- 6806 森崴能源 各路徑 ----
    def test_6806_disclosure_and_halt(self):
        r = score_news("森崴能源重大訊息待公布 暫停交易")
        self.assertIn(r["risk_level"], ("高", "極高"))
        self.assertIn("交易限制", r["dimensions"])

    def test_6806_change_trading_method(self):
        r = score_news("森崴能源改列變更交易方法")
        self.assertIn(r["risk_level"], ("高", "極高"))
        self.assertIn("變更交易方法", r["matched_terms"])

    def test_6806_negative_equity_and_split_auction(self):
        r = score_news("森崴能源淨值轉負 改分盤集合競價")
        self.assertIn(r["risk_level"], ("高", "極高"))
        self.assertIn("財務危機", r["dimensions"])
        self.assertIn("交易限制", r["dimensions"])

    def test_6806_delisting(self):
        r = score_news("森崴能源確定終止上市")
        self.assertIn(r["risk_level"], ("高", "極高"))
        self.assertIn("退場風險", r["dimensions"])

    # ---- 平緩語氣但高風險詞密集，不被「營運正常」洗白 ----
    def test_calm_tone_high_risk_not_whitewashed(self):
        r = score_news("公司公告：配合調查、財務長請辭、更換會計師，營運正常")
        self.assertIn(r["risk_level"], ("高", "極高"))
        self.assertGreaterEqual(len(r["dimensions"]), 2)
        self.assertIn("遭調查", r["matched_terms"])

    # ---- 同一詞重複不應線性灌爆 ----
    def test_repeated_term_not_linear(self):
        once = score_news("暫停交易")
        thrice = score_news("暫停交易 暫停交易 暫停交易")
        self.assertEqual(once["risk_score"], thrice["risk_score"])
        self.assertEqual(once["matched_terms"], thrice["matched_terms"])

    def test_cross_dimension_bonus(self):
        # 財務危機(5) + 交易限制(4) + 跨維度 bonus(2) = 11
        r = score_news("淨值轉負 並 暫停交易")
        self.assertEqual(r["risk_score"], 11)

    def test_benign_headline_zero_risk(self):
        r = score_news("公司召開法說會 營運展望")
        self.assertEqual(r["risk_score"], 0)
        self.assertEqual(r["risk_level"], "無")

    def test_summary_escalates_on_critical(self):
        risks = [score_news("終止上市"), score_news("淨值轉負"), score_news("法說會")]
        summary = build_risk_summary(risks)
        self.assertEqual(summary["level"], "警戒")
        self.assertTrue(summary["top_dimensions"])
        self.assertEqual(contains_forbidden(" ".join(summary["reasons"])), [])

    def test_rolling_windows(self):
        dated = [(date(2026, 6, 16), 5), (date(2026, 6, 1), 3), (date(2026, 5, 1), 2)]
        w = rolling_risk(dated, date(2026, 6, 17))
        self.assertEqual(w["d7"], 5)   # 只有 6/16 落在近 7 天
        self.assertEqual(w["d45"], 8)  # 5/1 已超過 45 天被排除
        self.assertIn("heating", w)

    def test_payload_no_advice_or_prediction(self):
        rss = (
            '<rss><channel>'
            '<item><title>某公司淨值轉負 暫停交易 - 報</title><link>x</link>'
            '<pubDate>Mon, 16 Jun 2025 01:00:00 GMT</pubDate></item>'
            '</channel></rss>'
        )
        payload = build_news_payload("6806", "森崴能源", rss)
        self.assertIn("risk", payload["items"][0])
        self.assertIn("risk_summary", payload)
        blob = " ".join(payload["risk_summary"].get("reasons", [])) + " " + str(payload["overall"])
        self.assertEqual(contains_forbidden(blob), [])


if __name__ == "__main__":
    unittest.main()
