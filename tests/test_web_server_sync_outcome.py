from __future__ import annotations

import unittest
from datetime import datetime

from app.sync.service import SyncResult
from app.web.server import _sync_outcome_payload


class SyncOutcomePayloadTests(unittest.TestCase):
    def test_partial_sync_result_gets_plain_language_retry_message(self) -> None:
        now = datetime(2026, 6, 30, 10, 55, 0)
        result = SyncResult(
            stock_id="1342",
            rows_written=252,
            started_at=now,
            finished_at=now,
            message="Rows were written but coverage still did not reach the target date.",
            gap_plan={"target_date": "2026-06-29", "local_latest_date": "2026-02-26"},
            coverage={"status": "suspect", "latest_date": "2026-02-26", "target_date": "2026-06-29"},
            post_status={"status": "suspect"},
            price_warning_count=42,
            first_price_warning="Skipped 1342 2026-06 daily prices: Cannot fetch TWSE url",
        )

        payload = _sync_outcome_payload(result)

        self.assertEqual(payload["status"], "partial")
        self.assertFalse(payload["current"])
        self.assertTrue(payload["needs_retry"])
        self.assertIn("1342 有補進 252 筆", str(payload["user_message"]))
        self.assertIn("42 個月份抓取失敗", str(payload["user_message"]))

    def test_patched_sync_result_is_current(self) -> None:
        now = datetime(2026, 6, 30, 10, 55, 0)
        result = SyncResult(
            stock_id="1342",
            rows_written=252,
            started_at=now,
            finished_at=now,
            message="Coverage reached the target date after patching.",
            gap_plan={"target_date": "2026-06-29"},
            coverage={"status": "patched", "latest_date": "2026-06-29", "target_date": "2026-06-29"},
            post_status={"status": "patched"},
        )

        payload = _sync_outcome_payload(result)

        self.assertEqual(payload["status"], "current")
        self.assertTrue(payload["current"])
        self.assertFalse(payload["needs_retry"])
        self.assertIn("已補到最近收盤 2026-06-29", str(payload["user_message"]))


if __name__ == "__main__":
    unittest.main()
