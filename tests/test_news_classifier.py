import unittest
from urllib.parse import unquote_plus

from app.news.classifier import (
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    build_overall_sentence,
    classify_headline,
    contains_forbidden,
    detect_events,
    load_lexicon,
)
from app.news.service import (
    build_news_payload,
    fetch_company_news,
    google_events_rss_url,
    google_news_rss_url,
    overall_label,
)


def _rss(titles):
    items = "".join(
        f"<item><title>{t}</title><link>https://x/{i}</link>"
        f"<pubDate>Mon, 16 Jun 2025 0{i}:00:00 GMT</pubDate></item>"
        for i, t in enumerate(titles)
    )
    return f'<?xml version="1.0"?><rss><channel>{items}</channel></rss>'


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>台積電營收創新高 法人看好後市 - 經濟日報</title><link>https://a</link>
<pubDate>Mon, 16 Jun 2025 01:00:00 GMT</pubDate></item>
<item><title>某電子認列虧損 下修財測 - 工商時報</title><link>https://b</link>
<pubDate>Mon, 16 Jun 2025 02:00:00 GMT</pubDate></item>
<item><title>公司召開股東常會 通過議案 - 中央社</title><link>https://c</link>
<pubDate>Mon, 16 Jun 2025 03:00:00 GMT</pubDate></item>
</channel></rss>"""


class NewsClassifierTest(unittest.TestCase):
    def test_positive_headline(self):
        verdict = classify_headline("台積電營收創新高 接獲大單")
        self.assertEqual(verdict.label, LABEL_POSITIVE)
        self.assertGreater(verdict.score, 0)
        self.assertTrue(any("創新高" in kw for kw in verdict.matched_positive))

    def test_negative_headline(self):
        verdict = classify_headline("公司由盈轉虧 下修財測 遭調降評等")
        self.assertEqual(verdict.label, LABEL_NEGATIVE)
        self.assertLess(verdict.score, 0)

    def test_neutral_headline(self):
        verdict = classify_headline("公司召開股東常會")
        self.assertEqual(verdict.label, LABEL_NEUTRAL)
        self.assertEqual(verdict.score, 0)

    def test_mixed_headline_is_neutral_when_balanced(self):
        # 同權重正反字眼互抵 → 中性（改善 1 對 競爭加劇 1）
        verdict = classify_headline("毛利改善但競爭加劇")
        self.assertEqual(verdict.label, LABEL_NEUTRAL)

    def test_overall_sentence_has_no_forbidden_words(self):
        sentence = build_overall_sentence(positive=3, negative=1, neutral=2, days=14)
        self.assertEqual(contains_forbidden(sentence), [])
        self.assertIn("非投資建議", sentence)

    def test_overall_sentence_empty(self):
        sentence = build_overall_sentence(positive=0, negative=0, neutral=0, days=14)
        self.assertIn("沒有抓到", sentence)

    def test_contains_forbidden_detects_violations(self):
        self.assertTrue(contains_forbidden("建議買進，目標價上看百元，會漲"))

    def test_build_news_payload_counts_and_tags(self):
        payload = build_news_payload("2330", "台積電", SAMPLE_RSS, days=14)
        self.assertEqual(payload["status"], "available")
        self.assertEqual(len(payload["items"]), 3)
        counts = payload["counts"]
        self.assertEqual(counts[LABEL_POSITIVE], 1)
        self.assertEqual(counts[LABEL_NEGATIVE], 1)
        self.assertEqual(counts[LABEL_NEUTRAL], 1)
        # 標題的「媒體」應被切出，title 不含 " - 經濟日報"
        first = payload["items"][0]
        self.assertNotIn(" - ", first["title"])
        self.assertEqual(first["source"], "經濟日報")
        self.assertEqual(contains_forbidden(payload["overall"]), [])

    def test_rss_url_contains_market_locale(self):
        url = google_news_rss_url("2330", "台積電", days=14)
        self.assertIn("hl=zh-TW", url)
        self.assertIn("when:14d", url.replace("%3A", ":").replace("%20", " ").replace("+", " "))

    def test_weighted_strong_keyword_outweighs_single_weak(self):
        # 漲停(2) 對上 下滑(1) → 仍偏多
        verdict = classify_headline("早盤亮燈漲停 但出貨略下滑")
        self.assertEqual(verdict.label, LABEL_POSITIVE)

    def test_load_lexicon_returns_weighted_dicts(self):
        positive, negative = load_lexicon()
        self.assertIsInstance(positive, dict)
        self.assertIn("漲停", positive)
        self.assertEqual(positive["漲停"], 2)
        self.assertTrue(all(isinstance(v, int) for v in positive.values()))

    def test_custom_lexicon_injection(self):
        verdict = classify_headline("公司宣布全新計畫", positive={"全新計畫": 1}, negative={})
        self.assertEqual(verdict.label, LABEL_POSITIVE)

    def test_supply_chain_keyword_expansion(self):
        verdict = classify_headline("公司取得長約 新品放量 產能利用率提升")
        self.assertEqual(verdict.label, LABEL_POSITIVE)
        self.assertGreater(verdict.score, 0)
        self.assertIn("取得長約", verdict.matched_positive)
        events = detect_events("公司取得長約 新品放量 產能利用率提升")
        self.assertIn("合作訂單", events)
        self.assertIn("供需價格", events)

    def test_reporting_control_and_cybersecurity_expansion(self):
        reporting = "公司未如期公告財報 內控缺失"
        reporting_verdict = classify_headline(reporting)
        self.assertEqual(reporting_verdict.label, LABEL_NEGATIVE)
        self.assertIn("財報內控", detect_events(reporting))

        cyber = "公司遭勒索軟體攻擊 資料外洩"
        cyber_verdict = classify_headline(cyber)
        self.assertEqual(cyber_verdict.label, LABEL_NEGATIVE)
        self.assertIn("資安事件", detect_events(cyber))

    def test_payload_sanitizes_generated_reason_words(self):
        raw = _rss(["某公司目標價上調 加碼投資 - 報"])
        payload = build_news_payload("9999", "測試公司", raw)
        reason = str(payload["items"][0]["reason"])  # type: ignore[index]
        self.assertEqual(contains_forbidden(reason), [])

    def test_major_event_tags_catch_delisting_warning_path(self):
        early = "森崴能源因重大訊息待公布 5/13暫停交易"
        early_verdict = classify_headline(early)
        self.assertEqual(early_verdict.label, LABEL_NEGATIVE)
        self.assertIn("重大訊息", detect_events(early))
        self.assertIn("交易限制", detect_events(early))

        trading_limit = "證交所公告森崴能源4/7列為變更交易方法"
        trading_events = detect_events(trading_limit)
        self.assertIn("交易限制", trading_events)
        self.assertIn("政策法規", trading_events)

        net_worth = "森崴能源第一季財報淨值轉負 將加採分盤集合競價"
        net_worth_verdict = classify_headline(net_worth)
        net_worth_events = detect_events(net_worth)
        self.assertEqual(net_worth_verdict.label, LABEL_NEGATIVE)
        self.assertIn("財務危機", net_worth_events)
        self.assertIn("退場風險", net_worth_events)
        self.assertIn("交易限制", net_worth_events)

        delisting = "森崴能源將於6/23終止上市"
        self.assertIn("退場風險", detect_events(delisting))

    def test_build_news_payload_surfaces_major_event_summary(self):
        raw = _rss([
            "森崴能源因重大訊息待公布 5/13暫停交易 - 公告",
            "森崴能源第一季財報淨值轉負 將加採分盤集合競價 - 新聞",
            "森崴能源將於6/23終止上市 - 新聞",
        ])
        payload = build_news_payload("6806", "森崴能源", raw, days=45)
        self.assertEqual(payload["counts"][LABEL_NEGATIVE], 3)
        self.assertIn("交易限制", payload["recent_events"])
        self.assertIn("退場風險", payload["recent_events"])
        self.assertIn("財務危機", payload["recent_events"])

    def test_event_search_uses_longer_window_and_risk_terms(self):
        url = google_events_rss_url("6806", "森崴能源", days=14)
        decoded = unquote_plus(url)
        self.assertIn("when:45d", decoded)
        self.assertIn("變更交易方法", decoded)
        self.assertIn("分盤集合競價", decoded)
        self.assertIn("終止上市", decoded)

    def test_overall_label_values(self):
        self.assertEqual(overall_label(3, 0, 1), "偏多")
        self.assertEqual(overall_label(0, 3, 1), "偏空")
        self.assertEqual(overall_label(1, 1, 2), "中性")
        self.assertEqual(overall_label(0, 0, 0), "無消息")

    def test_fetch_company_news_merges_and_dedupes_sources(self):
        google = _rss(["台積電創新高 - A報", "共同新聞標題 - A報"])
        bing = _rss(["共同新聞標題 - B報", "台積電獲利衰退 - B報"])

        def fake_fetch(url, timeout):
            return google if "google" in url else bing

        payload = fetch_company_news("2330", "台積電", fetch=fake_fetch)
        self.assertEqual(payload["status"], "available")
        titles = [item["title"] for item in payload["items"]]
        self.assertEqual(titles.count("共同新聞標題"), 1)  # 跨來源去重
        self.assertEqual(len(payload["items"]), 3)
        self.assertIn(payload["overall_label"], {"偏多", "偏空", "中性"})
        self.assertEqual(contains_forbidden(payload["overall"]), [])

    def test_fetch_company_news_all_sources_fail_degrades(self):
        def boom(url, timeout):
            raise OSError("no network")

        payload = fetch_company_news("2330", "台積電", fetch=boom)
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
