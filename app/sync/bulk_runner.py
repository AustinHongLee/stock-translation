"""把一鍵全下載接到真實 TWSE + 本地 DB。

效率關鍵：全市場共用檔（清單／股利／財報／營收／估值／三大法人）只在 prelude 抓一次並分發，
逐檔迴圈只抓『該檔日線歷史』（這是唯一無法整批拿的部分）。
所有 store/client 都在背景工作執行緒內建立（SQLite 連線綁定該執行緒）。
"""
from __future__ import annotations

from datetime import date, timedelta

from app.analyze.dividends import (
    dedupe_dividend_records as _dedupe_dividend_records,
    dividend_history_start_date,
)
from app.analyze.data_gap import DATA_NODE_DAILY_PRICE, previous_business_day
from app.analyze.twse_calendar import is_twse_trading_day
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
    # 目標 = 「今天之前的最後一個交易日」（節假日感知）。
    # 不可用 previous_business_day(today)：它在交易日會回傳今天本身，
    # 會讓盤中／收盤前所有股票都被判定『未到最新』。
    # 這裡刻意與 market_calendar.previous_completed_business_day（local-data 用的 expected）對齊。
    target_date = previous_business_day(today - timedelta(days=1))
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
                dividend_start = dividend_history_start_date(today)
                records = client.fetch_all_dividend_records()
                records.extend(client.fetch_all_historical_dividend_records(dividend_start, today))
                by_stock: dict[str, list] = {}
                for record in _dedupe_dividend_records(records):
                    by_stock.setdefault(record.stock_id, []).append(record)
                for sid, recs in by_stock.items():
                    store.upsert_dividend_records(recs)
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
            if is_twse_trading_day(day) and day_key not in have and day_key not in done_t86:
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
                store.refresh_data_coverage(sid, DATA_NODE_DAILY_PRICE, target_date=target_date)
        except Exception as exc:  # 真的抓取例外才 raise → 觸發連續失敗自動暫停保護
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "failed", error=str(exc))
            raise
        # 驗收：只有真的補到『最新交易日』才算 done。
        # fetch_daily_prices 會把個別月份失敗吞成 warning、不丟例外，
        # 若無條件標 done，半套／過期資料會被當成完成，且之後永遠被略過。
        # 因此一律用『本地實際最後一筆日期』驗收；未達標就標 failed（會被重試與下次下載重抓）。
        latest = store.get_daily_prices(sid, limit=1)
        if latest and latest[-1].date >= target_date:
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")
        else:
            have = latest[-1].date.isoformat() if latest else "無資料"
            store.mark_bulk_item(
                BULK_RUN_KEY,
                "stock",
                sid,
                "failed",
                error=(
                    f"日線未到最新交易日（最後={have}，目標={target_date.isoformat()}；"
                    "可能停牌／新上市／來源限流）"
                ),
            )

    def skip(sid: str) -> bool:
        store = ctx.get("store")
        if store is None:
            return False
        if retry_failed_only:
            return False
        # 重點修正：不再用 bulk_progress 的 "done" 短路。
        # 舊版只要曾標 done 就永遠跳過 → 過期股票即使重按全市場下載也補不回來。
        # 改成每次都用『本地最後一筆 vs 目標交易日』判斷新鮮度（精確、不用 <=3 天的近似）。
        latest = store.get_daily_prices(sid, limit=1)
        if latest and latest[-1].date >= target_date:
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")
            return True
        return False

    def on_finish(_status) -> None:
        store = ctx.get("store")
        client = ctx.get("client")
        # 1) 全市場最新一天日線 top-up（安全網）：用 STOCK_DAY_ALL 一次補齊所有人的最近收盤。
        #    放在收尾、不放 prelude——若放 prelude，首次下載會讓 skip() 看到『已有最新一根』
        #    而略過逐檔歷史回補，導致每檔只剩 1 根。逐檔遇限流時，這一筆能把最後一根補上。
        if client is not None and store is not None and not retry_failed_only:
            try:
                latest_all = client.fetch_latest_all_prices()
                if latest_all:
                    store.upsert_daily_prices(latest_all)
            except Exception:  # noqa: BLE001 - 安全網失敗不影響主流程
                pass
        # 2) 同步刷新雷達快照：讓『全市場下載』也更新 value_screener。
        #    否則快照停在上次『更新雷達』的日期 → 本地資料每列都掛『快照待更新』。
        #    這一步把兩個原本各走各的更新動作（全市場下載 / 更新雷達）綁在一起。
        if client is not None and not retry_failed_only:
            try:
                from app.screener.value import refresh_value_screener

                refresh_value_screener(client)
            except Exception:  # noqa: BLE001
                pass
        if store is not None:
            store.delete_json_cache("local_data_v2")

    return BulkPlan(
        list_stocks=list_stocks,
        sync_one=sync_one,
        prelude=prelude,
        skip=skip,
        on_finish=on_finish,
        retry_failed_only=retry_failed_only,
    )
