"""把一鍵全下載接到真實 TWSE + 本地 DB。

效率關鍵：全市場共用檔（清單／股利／財報／營收／估值／三大法人）只在 prelude 抓一次並分發，
逐檔迴圈只抓『該檔日線歷史』（這是唯一無法整批拿的部分）。
所有 store/client 都在背景工作執行緒內建立（SQLite 連線綁定該執行緒）。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.sync.bulk import BulkPlan
from app.sync.twse import TwseClient
from app.store.sqlite_store import SQLiteStore

T86_MAX_EMPTY = 12  # 連續無資料日就停（假期/邊界）
BULK_RUN_KEY = "full_market"


def build_bulk_plan(
    db_path,
    *,
    lookback_days: int = 365,
    request_interval: float = 0.2,
    retry_failed_only: bool = False,
) -> BulkPlan:
    ctx: dict = {}
    today = date.today()
    start = today - timedelta(days=max(1, lookback_days))

    def prelude(stop_event) -> None:
        store = SQLiteStore(db_path)
        client = TwseClient(request_interval=request_interval)
        ctx["store"] = store
        ctx["client"] = client

        if retry_failed_only:
            ctx["ids"] = store.get_bulk_item_keys_by_status(BULK_RUN_KEY, "stock", "failed")
            return

        # 1) 上市清單（必要；失敗就讓整批報錯）
        profiles = client.fetch_listed_profiles()
        store.upsert_profiles(profiles)
        ctx["ids"] = [p.stock_id for p in profiles]
        store.ensure_bulk_items(BULK_RUN_KEY, "stock", ctx["ids"])
        if stop_event.is_set():
            return

        # 2) 全市場共用檔，各抓一次（加值資料，失敗不阻斷）
        for fetch, save in (
            (client.fetch_all_monthly_revenues, store.upsert_monthly_revenues),
            (client.fetch_all_market_valuations, store.upsert_market_valuations),
            (client.fetch_all_financial_statements, store.upsert_financial_statements),
        ):
            if stop_event.is_set():
                return
            try:
                save(fetch())
            except Exception:  # noqa: BLE001
                pass

        # 3) 股利（一次，分組存）
        if not stop_event.is_set():
            try:
                by_stock: dict[str, list] = {}
                for record in client.fetch_all_dividend_records():
                    by_stock.setdefault(record.stock_id, []).append(record)
                for sid, recs in by_stock.items():
                    store.replace_dividend_records(sid, recs)
            except Exception:  # noqa: BLE001
                pass

        # 4) 三大法人 T86：近一年交易日，跳過已存日期、連續無資料就停
        have = store.get_institutional_dates_any()
        done_t86 = {
            key
            for key, status in store.get_bulk_item_statuses(BULK_RUN_KEY, "t86_date").items()
            if status == "done"
        }
        day = today
        empty = 0
        while day >= start and not stop_event.is_set():
            day_key = day.isoformat()
            if day.weekday() < 5 and day_key not in have and day_key not in done_t86:
                fetch_failed = False
                try:
                    trades = client.fetch_institutional_trades_for_date(day)
                except Exception:  # noqa: BLE001
                    trades = []
                    fetch_failed = True
                    store.mark_bulk_item(BULK_RUN_KEY, "t86_date", day_key, "failed")
                if trades:
                    store.upsert_institutional_trades(trades)
                    empty = 0
                else:
                    empty += 1
                if not fetch_failed:
                    store.mark_bulk_item(BULK_RUN_KEY, "t86_date", day_key, "done")
                if empty >= T86_MAX_EMPTY:
                    break
            day -= timedelta(days=1)

    def list_stocks() -> list[str]:
        return list(ctx.get("ids", []))

    def sync_one(sid: str) -> None:
        store = ctx["store"]
        client = ctx["client"]
        store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "running")
        try:
            prices = client.fetch_daily_prices(sid, start, today)
            if prices:
                store.upsert_daily_prices(prices)
        except Exception as exc:
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "failed", error=str(exc))
            raise
        store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")

    def skip(sid: str) -> bool:
        store = ctx.get("store")
        if store is None:
            return False
        if retry_failed_only:
            return False
        status = store.get_bulk_item_statuses(BULK_RUN_KEY, "stock").get(sid)
        if status == "done":
            return True
        latest = store.get_daily_prices(sid, limit=1)
        if not latest:
            return False
        fresh = (today - latest[-1].date).days <= 3
        if fresh:
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")
        return fresh

    def on_finish(_status) -> None:
        store = ctx.get("store")
        if store is not None:
            store.delete_json_cache("local_data_v1")

    return BulkPlan(
        list_stocks=list_stocks,
        sync_one=sync_one,
        prelude=prelude,
        skip=skip,
        on_finish=on_finish,
        retry_failed_only=retry_failed_only,
    )
