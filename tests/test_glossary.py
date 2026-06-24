from __future__ import annotations

import unittest

from app.glossary.service import glossary_payload, load_glossary

FORBIDDEN_UI_WORDS = ("便宜價", "合理價", "昂貴價", "低估", "高估", "該買", "該賣", "會漲", "會跌")


class GlossaryTests(unittest.TestCase):
    def test_glossary_payload_contains_terms_and_aliases(self) -> None:
        entries = load_glossary()
        payload = glossary_payload()

        self.assertGreaterEqual(len(entries), 10)
        self.assertIn("價格位階", payload["aliases"])
        self.assertEqual(payload["aliases"]["最新收盤"], "收盤價")  # type: ignore[index]
        self.assertTrue(any(entry.term == "EPS" for entry in entries))

    def test_beginner_terms_have_reminders(self) -> None:
        payload = glossary_payload()
        aliases = payload["aliases"]  # type: ignore[assignment]
        entries = payload["entries"]  # type: ignore[assignment]
        terms = {entry["term"]: entry for entry in entries}  # type: ignore[index]

        for term in (
            "每股淨值", "填息 / 貼息", "融資融券", "借券賣出", "ETF",
            "停損 / 停利", "複利", "分散風險", "流動性", "市值",
            "振幅", "年化波動度", "VWAP", "支撐 / 壓力",
            "延續性", "複雜度", "波動聚集", "噪音色", "湍流程度", "同步性",
        ):
            self.assertIn(term, terms)
            self.assertGreater(len(str(terms[term]["reminder"])), 8)
        self.assertEqual(aliases["BVPS"], "每股淨值")
        self.assertEqual(aliases["貼息"], "填息 / 貼息")
        self.assertEqual(aliases["指數股票型基金"], "ETF")
        self.assertEqual(aliases["波動度"], "年化波動度")
        self.assertEqual(aliases["波撐"], "支撐 / 壓力")
        self.assertEqual(aliases["排列熵"], "複雜度")
        self.assertEqual(aliases["市場同步"], "同步性")

    def test_glossary_public_text_avoids_project_redline_words(self) -> None:
        payload = glossary_payload()
        text = str(payload)

        for forbidden in FORBIDDEN_UI_WORDS:
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
