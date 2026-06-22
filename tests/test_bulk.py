import time
import unittest

from app.sync.bulk import BulkDownloadManager, BulkPlan


def _wait(cond, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class BulkManagerTest(unittest.TestCase):
    def test_normal_run_completes(self):
        m = BulkDownloadManager()
        done_ids = []
        plan = BulkPlan(list_stocks=lambda: ["A", "B", "C", "D", "E"],
                        sync_one=lambda sid: done_ids.append(sid))
        m.start(plan)
        self.assertTrue(_wait(lambda: m.status()["status"] == "done"))
        st = m.status()
        self.assertEqual(st["done"], 5)
        self.assertEqual(st["skipped"], 0)
        self.assertEqual(st["failed_count"], 0)
        self.assertEqual(sorted(done_ids), ["A", "B", "C", "D", "E"])

    def test_failures_auto_pause(self):
        m = BulkDownloadManager(max_consecutive_failures=2)
        def boom(sid):
            raise OSError("no network")
        plan = BulkPlan(list_stocks=lambda: ["A", "B", "C", "D", "E"], sync_one=boom)
        m.start(plan)
        self.assertTrue(_wait(lambda: m.status()["paused"]))
        st = m.status()
        self.assertEqual(st["status"], "paused")
        self.assertGreaterEqual(st["failed_count"], 2)
        m.stop()
        m.join(2)

    def test_skip(self):
        m = BulkDownloadManager()
        synced = []
        plan = BulkPlan(list_stocks=lambda: ["A", "B", "C", "D"],
                        sync_one=lambda sid: synced.append(sid),
                        skip=lambda sid: sid in {"B", "C"})
        m.start(plan)
        self.assertTrue(_wait(lambda: m.status()["status"] == "done"))
        st = m.status()
        self.assertEqual(st["skipped"], 2)
        self.assertEqual(sorted(synced), ["A", "D"])

    def test_status_reports_eta_when_running(self):
        m = BulkDownloadManager()
        plan = BulkPlan(list_stocks=lambda: [str(i) for i in range(20)],
                        sync_one=lambda sid: time.sleep(0.03))
        m.start(plan)
        self.assertTrue(_wait(lambda: (m.status()["done"] or 0) >= 2))
        st = m.status()
        self.assertIsNotNone(st["elapsed_seconds"])
        self.assertIsNotNone(st["eta_seconds"])
        self.assertIsNotNone(st["items_per_minute"])
        m.stop()
        m.join(2)

    def test_stop(self):
        m = BulkDownloadManager()
        plan = BulkPlan(list_stocks=lambda: [str(i) for i in range(80)],
                        sync_one=lambda sid: time.sleep(0.03))
        m.start(plan)
        self.assertTrue(_wait(lambda: m.status()["running"]))
        m.stop()
        self.assertTrue(_wait(lambda: m.status()["status"] == "stopped"))

    def test_single_instance_lock(self):
        m = BulkDownloadManager()
        plan = BulkPlan(list_stocks=lambda: [str(i) for i in range(40)],
                        sync_one=lambda sid: time.sleep(0.02))
        m.start(plan)
        self.assertTrue(_wait(lambda: m.status()["running"]))
        with self.assertRaises(RuntimeError):
            m.start(plan)
        m.stop()
        m.join(2)


if __name__ == "__main__":
    unittest.main()
