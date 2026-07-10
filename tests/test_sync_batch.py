from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.store.sqlite_store import SQLiteStore
from app.web.sync_batch import normalize_sync_targets
from app.web.server import _bulk_blocks_twse_fetch, _bulk_status


STATIC_DIR = Path("app/ui/static")
SERVER_PY = Path("app/web/server.py")


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
        server_py = SERVER_PY.read_text(encoding="utf-8")

        self.assertIn('id="bulkRetryFailedBtn"', html)
        self.assertIn('id="bulkHistoryBackfillBtn"', html)
        self.assertIn('id="bulkPlainStatus"', html)
        self.assertIn('id="bulkOutcomeList"', html)
        self.assertIn('id="bulkQueueDetail"', html)
        self.assertIn('data-bulk-queue="failed"', html)
        self.assertIn('id="dataSheet"', html)
        self.assertIn('id="bulkCard"', html)
        self.assertLess(html.index('id="dataSheet"'), html.index('id="bulkCard"'))
        self.assertIn("bulkRetryFailed", js)
        self.assertIn("bulkStartHistoryBackfill", js)
        self.assertIn("include_history_backfill", js)
        self.assertIn("include_history_backfill", server_py)
        self.assertIn("include_history_backfill=include_history_backfill", server_py)
        self.assertIn("加速補歷史", js)
        self.assertIn('postJson("/api/bulk-download/retry-failed"', js)
        self.assertIn("formatDuration(st.eta_seconds)", js)
        self.assertIn("failedCount === 0", js)
        self.assertIn("renderBulkPlainStatus", js)
        self.assertIn("bulkStatusCounts", js)
        self.assertIn("quietSyncHint", js)
        self.assertIn("failedRetryHint", js)
        self.assertIn("failed_retry", js)
        self.assertIn("repair_queue", js)
        self.assertIn("queue_details", js)
        self.assertIn("selectBulkQueueCategory", js)
        self.assertIn("renderBulkQueueDetail", js)
        self.assertIn("data-screener-stock", js)
        self.assertIn("source_retry", js)
        self.assertIn("sourcePendingHint", js)
        self.assertIn("可重新檢查", js)
        self.assertIn("can_retry_failed === false", js)
        self.assertIn("ready_count", js)
        self.assertIn("冷卻中的約", js)
        self.assertIn("每輪最多補", js)
        self.assertIn("正在冷卻", js)
        self.assertIn("history_pending_count", js)
        self.assertIn("歷史待背景", js)
        self.assertIn("這不是失敗", js)
        self.assertIn("isFreshButShallowGap", js)
        self.assertIn("歷史待補", js)
        self.assertIn("需補整段", js)
        self.assertIn("背景會慢慢補歷史", js)
        self.assertIn("日線樣本較短", js)
        self.assertIn("不是同步失敗", js)
        self.assertIn("日線資料落後", js)
        self.assertNotIn("日線資料過期 ${priceWindow.stale_days} 天", js)
        self.assertIn(".bulk-plain-status", css)
        self.assertIn(".bulk-outcomes", css)
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

    def test_bulk_running_blocks_other_twse_fetches(self) -> None:
        running = {"running": True, "paused": False, "status": "running"}
        paused = {"running": False, "paused": True, "status": "paused"}
        done = {"running": False, "paused": False, "status": "done"}

        for path in ("/api/sync", "/api/sync/batch", "/api/institutional/sync", "/api/value-screener/refresh"):
            self.assertTrue(_bulk_blocks_twse_fetch(path, running))
            self.assertTrue(_bulk_blocks_twse_fetch(path, paused))
            self.assertFalse(_bulk_blocks_twse_fetch(path, done))

        self.assertFalse(_bulk_blocks_twse_fetch("/api/bulk-download/stop", running))

    def test_bulk_status_disables_retry_failed_while_all_failed_items_are_cooling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.ensure_bulk_items("full_market", "stock", ["2330"])
                store.mark_bulk_item("full_market", "stock", "2330", "failed", error="TWSE busy")

            cooling = _bulk_status(db_path)
            self.assertFalse(cooling["can_retry_failed"])
            self.assertEqual(cooling["failed_retry"]["ready_count"], 0)  # type: ignore[index]
            self.assertEqual(cooling["queue_details"]["failed"]["items"][0]["stock_id"], "2330")  # type: ignore[index]
            self.assertEqual(cooling["queue_details"]["failed"]["items"][0]["retry_state"], "cooling")  # type: ignore[index]

            with SQLiteStore(db_path) as store:
                old = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
                store.conn.execute(
                    """
                    UPDATE bulk_progress
                    SET updated_at = ?
                    WHERE run_key = ? AND item_type = ? AND item_key = ?
                    """,
                    (old, "full_market", "stock", "2330"),
                )
                store.conn.commit()

            ready = _bulk_status(db_path)
            self.assertTrue(ready["can_retry_failed"])
            self.assertEqual(ready["failed_retry"]["ready_count"], 1)  # type: ignore[index]
            self.assertEqual(ready["queue_details"]["failed"]["items"][0]["retry_state"], "ready")  # type: ignore[index]

    def test_bulk_status_reports_source_pending_retry_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.ensure_bulk_items("full_market", "stock", ["2454"])
                store.mark_bulk_item("full_market", "stock", "2454", "source_pending", error="not published")

            cooling = _bulk_status(db_path)
            self.assertEqual(cooling["source_retry"]["ready_count"], 0)  # type: ignore[index]
            self.assertEqual(cooling["source_retry"]["cooling_down_count"], 1)  # type: ignore[index]
            self.assertEqual(cooling["queue_details"]["source_pending"]["items"][0]["retry_state"], "cooling")  # type: ignore[index]

            with SQLiteStore(db_path) as store:
                old = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
                store.conn.execute(
                    """
                    UPDATE bulk_progress
                    SET updated_at = ?
                    WHERE run_key = ? AND item_type = ? AND item_key = ?
                    """,
                    (old, "full_market", "stock", "2454"),
                )
                store.conn.commit()

            ready = _bulk_status(db_path)
            self.assertEqual(ready["source_retry"]["ready_count"], 1)  # type: ignore[index]
            self.assertEqual(ready["queue_details"]["source_pending"]["items"][0]["retry_state"], "ready")  # type: ignore[index]

    def test_user_sync_mentions_quiet_preemption_notice(self) -> None:
        js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("trafficControlNotice", js)
        self.assertIn("preempted_quiet_sync", js)
        self.assertIn("背景補資料已暫停並讓路", js)


if __name__ == "__main__":
    unittest.main()
