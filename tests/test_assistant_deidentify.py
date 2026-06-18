from __future__ import annotations

import json
import unittest

from app.assistant.deidentify import DeidentifyOptions, deidentify_payload


class AssistantDeidentifyTests(unittest.TestCase):
    def test_deidentify_removes_private_notes_and_masks_amounts(self) -> None:
        payload = {
            "summary": {
                "total_market_value": 1_234_567,
                "total_unrealized_pnl": -55_000,
                "total_unrealized_return_percent": -4.5,
            },
            "positions": [
                {
                    "stock_id": "2330",
                    "shares": 1000,
                    "average_cost": 600,
                    "note": "朋友電話 0912-345-678 email me@example.com",
                    "created_at": "2026-06-01T10:00:00",
                }
            ],
        }

        result = deidentify_payload(payload)
        text = json.dumps(result, ensure_ascii=False)

        self.assertIn("2330", text)
        self.assertIn("百萬元級", text)
        self.assertIn("萬元級", text)
        self.assertNotIn("0912", text)
        self.assertNotIn("me@example.com", text)
        self.assertNotIn("朋友電話", text)
        self.assertNotIn("created_at", text)
        self.assertEqual(result["summary"]["total_unrealized_return_percent"], -4.5)

    def test_deidentify_can_keep_amounts_when_explicitly_disabled(self) -> None:
        payload = {"summary": {"total_market_value": 1234}}

        result = deidentify_payload(
            payload,
            options=DeidentifyOptions(mask_amounts=False),
        )

        self.assertEqual(result["summary"]["total_market_value"], 1234)


if __name__ == "__main__":
    unittest.main()
