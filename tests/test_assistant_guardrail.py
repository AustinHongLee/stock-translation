from __future__ import annotations

import unittest

from app.assistant.context_builder import build_assistant_context
from app.assistant.fallback import build_fallback_response
from app.assistant.guardrail import (
    SAFE_FALLBACK_MESSAGE,
    check_output_guardrail,
    check_request_guardrail,
    guard_assistant_output,
)


class AssistantGuardrailTests(unittest.TestCase):
    def test_output_guardrail_blocks_trading_or_prediction_language(self) -> None:
        samples = [
            "這檔可以買，目標價 100。",
            "明天會漲，適合加碼。",
            "跌破 50 就停損。",
            "這是今天的明牌。",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                result = check_output_guardrail(sample)
                self.assertFalse(result.allowed)
                self.assertTrue(result.matched_terms)

    def test_request_guardrail_blocks_recommendation_requests(self) -> None:
        result = check_request_guardrail("請推薦一支明天會漲的股票")

        self.assertFalse(result.allowed)
        self.assertIn("推薦", result.matched_terms)

    def test_safe_output_passes_and_unsafe_output_falls_back(self) -> None:
        safe = "這份資料只顯示近一年價格位置偏高，請搭配營收與獲利資料一起看。"
        unsafe = "這檔會漲，可以買。"

        self.assertTrue(check_output_guardrail(safe).allowed)
        self.assertEqual(guard_assistant_output(safe), safe)
        self.assertEqual(guard_assistant_output(unsafe), SAFE_FALLBACK_MESSAGE)

    def test_fallback_response_uses_structured_context_only(self) -> None:
        context = build_assistant_context(
            kind="stock",
            payload={
                "brief": {
                    "company_sentence": "台積電屬於半導體業。",
                    "valuation_sentence": "比較適合看本益比敏感度與營收動能。",
                },
                "report": {"sections": [{"title": "最近趨勢"}]},
                "valuation": {"suitability": {"state_label": "股利法參考性低"}},
            },
        )
        response = build_fallback_response(context)

        self.assertIn("台積電", response)
        self.assertNotIn("買進", response)
        self.assertNotIn("目標價", response)


if __name__ == "__main__":
    unittest.main()
