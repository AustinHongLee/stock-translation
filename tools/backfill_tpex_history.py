"""用上櫃「指定日期全市場」端點，漸進補齊官方 Data Hub 的近一年日線。

這支程式只供 GitHub Actions 維護共享 baseline。一次請求可取得整個上櫃市場，
避免 800 多檔股票各自逐月抓取；完成日期會寫入 baseline，重跑時不重複撞來源。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analyze.twse_calendar import is_twse_trading_day
from app.analyze.data_gap import DATA_NODE_DAILY_PRICE
from app.store.sqlite_store import SQLiteStore
from app.sync.tpex import TpexClient

MARKET = "TPEX"
NODE = DATA_NODE_DAILY_PRICE
MARKER_TABLE = "hub_backfill_days"


def backfill_tpex_history(
    db_path: Path,
    *,
    history_days: int = 370,
    max_days: int = 40,
    request_interval: float = 0.35,
    client: TpexClient | Any | None = None,
) -> dict[str, object]:
    db_path = db_path.resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"baseline DB 不存在：{db_path}")
    history_days = max(1, int(history_days))
    max_days = max(1, int(max_days))
    client = client or TpexClient(request_interval=request_interval)

    processed_days = 0
    rows_written = 0
    warnings: list[str] = []
    touched_stock_ids: set[str] = set()

    with SQLiteStore(db_path) as store:
        _ensure_marker_table(store)
        stock_ids = _tpex_stock_ids(store)
        if not stock_ids:
            return {
                "publish": False,
                "processed_days": 0,
                "rows": 0,
                "remaining_days": 0,
                "summary": "baseline 沒有上櫃股票清單，未補歷史。",
            }

        end_day = _latest_daily_day(store)
        if end_day is None:
            return {
                "publish": False,
                "processed_days": 0,
                "rows": 0,
                "remaining_days": 0,
                "summary": "baseline 沒有已確認的最新日，未補上櫃歷史。",
            }
        start_day = end_day - timedelta(days=history_days - 1)
        eligible = [
            day
            for day in _days_descending(start_day, end_day)
            if is_twse_trading_day(day)
        ]
        completed = _completed_days(store, start_day, end_day)
        pending = [day for day in eligible if day.isoformat() not in completed]
        consecutive_errors = 0

        for index, day in enumerate(pending[:max_days]):
            try:
                prices = client.fetch_all_daily_prices_for_date(
                    day, stock_ids=stock_ids
                )
                if prices:
                    store.upsert_daily_prices(prices)
                    rows_written += len(prices)
                    touched_stock_ids.update(item.stock_id for item in prices)
                _mark_completed(store, day, len(prices))
                processed_days += 1
                consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001 - 單日失敗留給下次重試
                warnings.append(f"{day.isoformat()}：{str(exc)[:100]}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    break
            if request_interval > 0 and index < min(len(pending), max_days) - 1:
                time.sleep(request_interval)

        if touched_stock_ids:
            for stock_id in stock_ids:
                store.refresh_data_coverage(
                    stock_id,
                    NODE,
                    target_date=end_day,
                    commit=False,
                )
            store.conn.commit()

        completed_after = _completed_days(store, start_day, end_day)
        remaining_days = sum(day.isoformat() not in completed_after for day in eligible)

    warning_text = f"；警告：{'；'.join(warnings[:3])}" if warnings else ""
    if processed_days:
        summary = (
            f"上櫃歷史補 {processed_days} 個交易日、寫入 {rows_written} 筆；"
            f"近 {history_days} 天尚餘 {remaining_days} 個交易日{warning_text}"
        )
    elif remaining_days == 0:
        summary = f"上櫃近 {history_days} 天歷史 baseline 已完整。"
    else:
        summary = f"上櫃歷史本輪未寫入，尚餘 {remaining_days} 個交易日{warning_text}"
    return {
        "publish": processed_days > 0,
        "processed_days": processed_days,
        "rows": rows_written,
        "remaining_days": remaining_days,
        "summary": summary,
    }


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(
        description="Backfill one year of TPEx history into a hub DB."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--history-days", type=int, default=370)
    parser.add_argument("--max-days", type=int, default=40)
    parser.add_argument("--request-interval", type=float, default=0.35)
    args = parser.parse_args()

    try:
        result = backfill_tpex_history(
            args.db,
            history_days=args.history_days,
            max_days=args.max_days,
            request_interval=max(0.0, args.request_interval),
        )
    except Exception as exc:  # noqa: BLE001
        print("publish=no")
        print(f"summary=上櫃歷史補齊無法啟動：{str(exc)[:180]}")
        return 2

    print(f"publish={'yes' if result['publish'] else 'no'}")
    print(f"processed_days={result['processed_days']}")
    print(f"rows={result['rows']}")
    print(f"remaining_days={result['remaining_days']}")
    print(f"summary={result['summary']}")
    return 0


def _ensure_marker_table(store: SQLiteStore) -> None:
    store.conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MARKER_TABLE} (
            market TEXT NOT NULL,
            node TEXT NOT NULL,
            date TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (market, node, date)
        )
        """
    )
    store.conn.commit()


def _tpex_stock_ids(store: SQLiteStore) -> set[str]:
    rows = store.conn.execute(
        "SELECT stock_id FROM stock_profiles WHERE UPPER(market) = ?",
        (MARKET,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _latest_daily_day(store: SQLiteStore) -> date | None:
    row = store.conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
    value = str(row[0] or "") if row else ""
    return date.fromisoformat(value) if value else None


def _completed_days(store: SQLiteStore, start_day: date, end_day: date) -> set[str]:
    rows = store.conn.execute(
        f"""
        SELECT date FROM {MARKER_TABLE}
        WHERE market = ? AND node = ? AND date BETWEEN ? AND ?
        """,
        (MARKET, NODE, start_day.isoformat(), end_day.isoformat()),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _mark_completed(store: SQLiteStore, day: date, row_count: int) -> None:
    completed_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    store.conn.execute(
        f"""
        INSERT INTO {MARKER_TABLE} (market, node, date, row_count, completed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(market, node, date) DO UPDATE SET
            row_count = excluded.row_count,
            completed_at = excluded.completed_at
        """,
        (MARKET, NODE, day.isoformat(), int(row_count), completed_at),
    )
    store.conn.commit()


def _days_descending(start_day: date, end_day: date):
    day = end_day
    while day >= start_day:
        yield day
        day -= timedelta(days=1)


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
