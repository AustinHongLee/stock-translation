from __future__ import annotations

import re
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.analyze.daily_digest import build_daily_digest
from app.analyze.price_alerts import alert_hits, alert_line, normalize_direction
from app.models import DailyPrice
from app.store.sqlite_store import SQLiteStore
from app.web.api import check_price_alerts

FORBIDDEN = re.compile(r"該買|該賣|買進|賣出|目標價|建議買|建議賣|看多|看空|停損|停利")


class AlertLogicTests(unittest.TestCase):
    def test_alert_hits_boundaries(self) -> None:
        self.assertTrue(alert_hits("above", 100.0, 100.0))
        self.assertTrue(alert_hits("above", 100.0, 101.0))
        self.assertFalse(alert_hits("above", 100.0, 99.9))
        self.assertTrue(alert_hits("below", 50.0, 50.0))
        self.assertTrue(alert_hits("below", 50.0, 49.0))
        self.assertFalse(alert_hits("below", 50.0, 50.1))
        self.assertFalse(alert_hits("weird", 50.0, 10.0))

    def test_normalize_direction(self) -> None:
        self.assertEqual(normalize_direction(" Above "), "above")
        self.assertEqual(normalize_direction("below"), "below")
        self.assertIsNone(normalize_direction("up"))
        self.assertIsNone(normalize_direction(None))

    def test_alert_line_is_neutral(self) -> None:
        line = alert_line(
            {
                "stock_id": "2330",
                "direction": "above",
                "price": 1050.0,
                "triggered_close": 1062.0,
                "triggered_date": "2026-08-06",
            },
            name="台積電",
        )
        self.assertIn("台積電", line)
        self.assertIn("1,062", line)
        self.assertIn("1,050 以上", line)
        self.assertIsNone(FORBIDDEN.search(line), line)


class AlertStoreFlowTests(unittest.TestCase):
    def test_check_marks_triggered_once_and_reports_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [DailyPrice("2330", date.today(), 1060, 1065, 1055, 1062.0, 1000)]
                )
                store.add_price_alert("2330", direction="above", price=1050.0)
                store.add_price_alert("2330", direction="below", price=900.0)  # 未到

                lines = check_price_alerts(store)
                self.assertEqual(len(lines), 1)
                self.assertIn("1,050 以上", lines[0])

                alerts = store.list_price_alerts("2330")
                triggered = [a for a in alerts if a["triggered_at"] is not None]
                waiting = [a for a in alerts if a["triggered_at"] is None]
                self.assertEqual(len(triggered), 1)
                self.assertEqual(len(waiting), 1)
                first_triggered_at = triggered[0]["triggered_at"]

                # 再跑一次：不重複標記（triggered_at 不變）、仍在近幾天內所以還會顯示
                lines2 = check_price_alerts(store)
                self.assertEqual(len(lines2), 1)
                alerts2 = store.list_price_alerts("2330")
                self.assertEqual(
                    [a["triggered_at"] for a in alerts2 if a["triggered_at"] is not None],
                    [first_triggered_at],
                )

    def test_old_triggers_fall_out_of_recent_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_daily_prices(
                    [DailyPrice("2330", date(2026, 6, 1), 1060, 1065, 1055, 1062.0, 1000)]
                )
                alert_id = store.add_price_alert("2330", direction="above", price=1050.0)
                store.mark_price_alert_triggered(
                    alert_id, close=1062.0, trade_date="2026-06-01"
                )
                lines = check_price_alerts(store)
                self.assertEqual(lines, [])  # 超過保留天數，不再洗版首頁

    def test_delete_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                alert_id = store.add_price_alert("2330", direction="below", price=900.0)
                self.assertEqual(len(store.list_price_alerts("2330")), 1)
                store.delete_price_alert(alert_id)
                self.assertEqual(store.list_price_alerts("2330"), [])


class DigestAlertLinesTests(unittest.TestCase):
    def test_digest_carries_alert_lines(self) -> None:
        items = [
            {
                "stock_id": "2330",
                "profile": {"short_name": "台積電"},
                "board": {
                    "name": "台積電",
                    "latest": {"close": 1062.0, "date": "2026-08-06", "change_percent": 0.5},
                    "data": {"rows": 200, "stale_days": 0},
                    "level": {"status": "區間中段"},
                },
            }
        ]
        digest = build_daily_digest(items, alert_lines=["⚑ 台積電 已到你設定的 1,050 以上"])
        assert digest is not None
        self.assertEqual(len(digest["alert_lines"]), 1)

    def test_alerts_show_even_without_watchlist(self) -> None:
        digest = build_daily_digest([], alert_lines=["⚑ 台積電 已到你設定的 1,050 以上"])
        assert digest is not None
        self.assertIn("1,050", digest["headline"])
        self.assertEqual(digest["movers"], [])

    def test_no_items_no_alerts_returns_none(self) -> None:
        self.assertIsNone(build_daily_digest([], alert_lines=[]))


if __name__ == "__main__":
    unittest.main()
