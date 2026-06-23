from __future__ import annotations

import unittest
from pathlib import Path

from app.web.sync_batch import normalize_sync_targets


STATIC_DIR = Path("app/ui/static")


class SyncBatchTests(unittest.TestCase):
    def test_normalize_sync_targets_dedupes_and_accepts_comma_text(self) -> None:
        self.assertEqual(
            normalize_sync_targets("2330, 0050，2330、2408"),
            ["2330", "0050", "2408"],
        )

    def test_normalize_sync_targets_rejects_invalid_or_too_many(self) -> None:
        with self.assertRaises(ValueError):
            normalize_sync_targets(["2330", "../bad"])
        with self.assertRaises(ValueError):
            normalize_sync_targets([str(1000 + i) for i in range(21)])

    def test_levels_card_has_batch_update_controls(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="levelsSyncButton"', html)
        self.assertIn("syncLevelsTargets", js)
        self.assertIn("syncLevelTarget", js)
        self.assertIn("data-level-sync-stock", js)
        self.assertIn("levels-row-actions", js)
        self.assertIn("LEVEL_SYNC_CONCURRENCY = 2", js)
        self.assertIn("syncTargetsConcurrently", js)
        self.assertIn("Promise.all", js)
        self.assertIn('postJson("/api/sync/batch"', js)
        self.assertIn("syncTargetsSequentially", js)
        self.assertIn('postJson("/api/sync"', js)
        self.assertIn("uniqueStockIds", js)

    def test_bulk_download_has_retry_failed_control_and_eta(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

        self.assertIn('id="bulkRetryFailedBtn"', html)
        self.assertIn('id="dataSheet"', html)
        self.assertIn('id="bulkCard"', html)
        self.assertLess(html.index('id="dataSheet"'), html.index('id="bulkCard"'))
        self.assertIn("bulkRetryFailed", js)
        self.assertIn('postJson("/api/bulk-download/retry-failed"', js)
        self.assertIn("formatDuration(st.eta_seconds)", js)
        self.assertIn("failedCount === 0", js)
        self.assertIn(".bulk-controls .chart-size-btn", css)
        self.assertIn("min-height: 38px", css)

    def test_screener_open_stock_does_not_trigger_sync(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn("async function openScreenerStock", js)
        self.assertIn("await openScreenerStock(button.dataset.screenerStock)", js)
        self.assertIn("await loadStock(target)", js)
        self.assertNotIn("await syncStock(button.dataset.screenerStock)", js)

    def test_sync_stock_checks_freshness_before_posting(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('/api/sync/freshness/', js)
        self.assertIn("freshness?.can_skip_sync", js)
        self.assertIn("skip_if_current: true", js)
        self.assertIn("已是最近收盤", js)


if __name__ == "__main__":
    unittest.main()
