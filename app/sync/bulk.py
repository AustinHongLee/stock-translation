"""一鍵全資料下載：背景任務管理器（含暫停／停止／斷點續傳／連續失敗自動暫停等保護）。

設計重點：
- 真正的網路抓取由外部注入的 Plan（prelude / list_stocks / sync_one / skip）負責，
  本管理器只負責「流程控制與保護」，因此可用 stub 做確定性單元測試。
- 跑在背景執行緒；UI 以 status() 輪詢。
- 單一任務鎖：同時只允許一個下載。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

MAX_CONSECUTIVE_FAILURES = 8  # 連續這麼多檔失敗就自動暫停（多半是斷線）


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class BulkPlan:
    """注入的抓取計畫。prelude/skip 可為 None。"""

    list_stocks: Callable[[], list[str]]
    sync_one: Callable[[str], None]
    prelude: Callable[[threading.Event], None] | None = None
    skip: Callable[[str], bool] | None = None
    on_finish: Callable[[dict[str, Any]], None] | None = None
    retry_failed_only: bool = False


class BulkDownloadManager:
    def __init__(self, *, max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pause = threading.Event()
        self._stop = threading.Event()
        self._max_consec = max(1, max_consecutive_failures)
        self._state: dict[str, Any] = {}
        self._started_monotonic: float | None = None
        self._reset_state()

    def _reset_state(self) -> None:
        self._state = {
            "status": "idle",  # idle / preparing / running / paused / stopped / done / error
            "total": 0,
            "done": 0,
            "skipped": 0,
            "current": None,
            "failed": [],  # [{stock_id, error}]
            "message": "",
            "started_at": None,
            "finished_at": None,
            "retry_failed_only": False,
        }

    # ---- 控制 ----
    def start(self, plan: BulkPlan) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("已有下載任務正在進行中。")
            self._pause.clear()
            self._stop.clear()
            self._reset_state()
            self._state["status"] = "preparing"
            self._state["started_at"] = _now()
            self._state["retry_failed_only"] = plan.retry_failed_only
            self._started_monotonic = time.monotonic()
            self._thread = threading.Thread(target=self._run, args=(plan,), daemon=True)
            self._thread.start()

    def pause(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._pause.set()
            self._update(status="paused", message="已暫停")

    def resume(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._pause.clear()
            self._update(status="running", message="")

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- 狀態 ----
    def status(self) -> dict[str, Any]:
        with self._lock:
            st = dict(self._state)
            st["failed"] = list(self._state["failed"])
            st["failed_count"] = len(self._state["failed"])
            st["running"] = self._thread is not None and self._thread.is_alive()
            st["paused"] = self._pause.is_set()
            st.update(self._timing_status(st))
            return st

    def _timing_status(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._started_monotonic is None:
            return {"elapsed_seconds": None, "eta_seconds": None, "items_per_minute": None}
        elapsed = max(0.0, time.monotonic() - self._started_monotonic)
        total = int(state.get("total") or 0)
        done = int(state.get("done") or 0)
        if total <= 0 or done <= 0 or done >= total:
            eta = None
        else:
            eta = round((elapsed / done) * (total - done))
        rate = (done / elapsed * 60) if elapsed > 0 and done > 0 else None
        return {
            "elapsed_seconds": round(elapsed),
            "eta_seconds": eta,
            "items_per_minute": round(rate, 2) if rate is not None else None,
        }

    def _update(self, **kw: Any) -> None:
        with self._lock:
            self._state.update(kw)

    def _add_failed(self, stock_id: str, error: str) -> None:
        with self._lock:
            self._state["failed"].append({"stock_id": stock_id, "error": str(error)[:200]})

    def _inc(self, key: str) -> None:
        with self._lock:
            self._state[key] = self._state.get(key, 0) + 1

    # ---- 主流程（可同步呼叫做測試） ----
    def _run(self, plan: BulkPlan) -> None:
        try:
            if plan.prelude is not None:
                self._update(status="preparing", message="抓取全市場共用資料（股利／財報／營收／估值／法人）…")
                plan.prelude(self._stop)
            if self._stop.is_set():
                self._update(status="stopped", finished_at=_now(), current=None, message="已停止")
                return

            ids = list(plan.list_stocks())
            self._update(status="running", total=len(ids), message="")
            consec = 0
            for i, sid in enumerate(ids):
                if self._stop.is_set():
                    self._update(status="stopped", done=i, current=None, finished_at=_now(), message="已停止")
                    return
                # 暫停：在每檔之間等待，期間可被停止
                while self._pause.is_set() and not self._stop.is_set():
                    time.sleep(0.2)
                if self._stop.is_set():
                    self._update(status="stopped", done=i, current=None, finished_at=_now(), message="已停止")
                    return

                self._update(current=sid, done=i)
                try:
                    if plan.skip is not None and plan.skip(sid):
                        self._inc("skipped")
                        continue
                    plan.sync_one(sid)
                    consec = 0
                except Exception as exc:  # noqa: BLE001 - 單檔失敗不中斷整批
                    self._add_failed(sid, str(exc))
                    consec += 1
                    if consec >= self._max_consec:
                        self._pause.set()
                        self._update(
                            status="paused",
                            message=f"連續 {consec} 檔失敗，已自動暫停（可能斷線）。排除問題後可按『繼續』。",
                        )
                        consec = 0

            if self._stop.is_set():
                self._update(status="stopped", current=None, finished_at=_now(), message="已停止")
            else:
                self._update(status="done", done=len(ids), current=None, finished_at=_now(), message="完成")
                if plan.on_finish is not None:
                    try:
                        plan.on_finish(self.status())
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001 - 整批層級錯誤
            self._update(status="error", current=None, finished_at=_now(), message=str(exc))


# 程序內單例（被 web 層共用）
BULK_MANAGER = BulkDownloadManager()
