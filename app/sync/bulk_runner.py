"""把一鍵全下載接到真實 TWSE + 本地 DB。

效率關鍵：全市場共用檔（清單／股利／財報／營收／估值／三大法人）只在 prelude 抓一次並分發，
逐檔迴圈只抓『該檔日線歷史』（這是唯一無法整批拿的部分）。
所有 store/client 都在背景工作執行緒內建立（SQLite 連線綁定該執行緒）。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.analyze.dividends import (
    dedupe_dividend_records as _dedupe_dividend_records,
    dividend_history_start_date,
)
from app.analyze.data_gap import (
    DATA_NODE_DAILY_PRICE,
    STATUS_CURRENT,
    STATUS_PATCHED,
    STATUS_SOURCE_PENDING,
    plan_data_gap,
    previous_business_day,
    resolve_post_patch_status,
    same_month_tail_date,
)
from app.analyze.twse_calendar import is_twse_trading_day
from app.models import DailyPrice
from app.sync.bulk import BulkPlan
from app.sync.twse import TwseClient
from app.store.sqlite_store import SQLiteStore

T86_MAX_EMPTY = 12  # 連續無資料日就停（假期/邊界）
# 最近 N 個交易日的法人「強制重抓」：治癒過去把『當下沒公布、回傳空』誤標 done 的日期，並確保最新。
# 法人是全市場逐日資料，補一天 = 補齊所有股票，所以這幾次 API 很划算。
T86_RECENT_FORCE_DAYS = 7
BULK_RUN_KEY = "full_market"
BULK_STATUS_SOURCE_PENDING = "source_pending"
BULK_FAILED_RETRY_BACKOFF_SECONDS = 30 * 60


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

        _top_up_latest_all_prices(store, client)

        if retry_failed_only:
            ctx["ids"] = store.get_bulk_item_keys_by_status(BULK_RUN_KEY, "stock", "failed")
            ctx["ids"] = _prioritized_stock_ids(ctx, ctx["ids"], target_date, lookback_days)
            return

        # 1) 上市清單（必要；失敗就讓整批報錯）
        profiles = client.fetch_listed_profiles()
        store.upsert_profiles(profiles)
        ctx["ids"] = [p.stock_id for p in profiles]
        # 上市日期供深度評估與抓取窗口 clamp（新上市股不空抓一年）。
        ctx["listed_dates"] = {
            p.stock_id: p.listed_date for p in profiles if p.listed_date is not None
        }
        store.ensure_bulk_items(BULK_RUN_KEY, "stock", ctx["ids"])
        ctx["ids"] = _prioritized_stock_ids(ctx, ctx["ids"], target_date, lookback_days)
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

        # 4) 三大法人 T86（全市場逐日資料：補一天 = 補齊所有股票）
        # 4a) 強制重抓最近 N 個交易日：治癒過去把「當下沒公布、回傳空」誤標成 done 的日期，並確保最新。
        #     不看 have/done，直接重抓（upsert 冪等）；只有真的抓到資料才標 done。
        day = today
        forced = 0
        while forced < T86_RECENT_FORCE_DAYS and day >= start and not stop_event.is_set():
            if is_twse_trading_day(day):
                forced += 1
                day_key = day.isoformat()
                try:
                    trades = client.fetch_institutional_trades_for_date(day)
                except Exception:  # noqa: BLE001
                    trades = []
                if trades:
                    store.upsert_institutional_trades(trades)
                    store.mark_bulk_item(BULK_RUN_KEY, "t86_date", day_key, "done")
            day -= timedelta(days=1)

        # 4b) 再往更早的歷史補：跳過已存／已完成日期、連續無資料就停。
        have = store.get_institutional_dates_any()
        done_t86 = {
            key
            for key, status in store.get_bulk_item_statuses(BULK_RUN_KEY, "t86_date").items()
            if status == "done"
        }
        empty = 0
        while day >= start and not stop_event.is_set():
            day_key = day.isoformat()
            if is_twse_trading_day(day) and day_key not in have and day_key not in done_t86:
                try:
                    trades = client.fetch_institutional_trades_for_date(day)
                except Exception:  # noqa: BLE001
                    trades = []
                    store.mark_bulk_item(BULK_RUN_KEY, "t86_date", day_key, "failed")
                if trades:
                    store.upsert_institutional_trades(trades)
                    # 只有真的有資料才標 done（空日不標，下次才會重抓，不再永久毒化）。
                    store.mark_bulk_item(BULK_RUN_KEY, "t86_date", day_key, "done")
                    empty = 0
                else:
                    empty += 1
                if empty >= T86_MAX_EMPTY:
                    break
            day -= timedelta(days=1)

    def list_stocks() -> list[str]:
        return list(ctx.get("ids", []))

    def sync_one(sid: str) -> None:
        store = ctx["store"]
        client = ctx["client"]
        store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "running")
        price_warnings: list[str] = []
        post_status = None
        try:
            coverage_before = store.refresh_data_coverage(
                sid,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
            )
            gap_plan = plan_data_gap(
                stock_id=sid,
                node=DATA_NODE_DAILY_PRICE,
                coverage=coverage_before,
                target_date=target_date,
                lookback_days=lookback_days,
                max_patch_business_days=45,
                listed_date=_listed_date_for(ctx, sid),
            )
            if gap_plan.status == STATUS_CURRENT:
                store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")
                return
            else:
                fetch_start = gap_plan.fetch_start_date or start
                fetch_end = gap_plan.fetch_end_date or target_date

            prices = client.fetch_daily_prices(sid, fetch_start, fetch_end)
            price_warnings = _dedupe_texts(list(getattr(client, "last_warnings", [])))
            tail_end = same_month_tail_date(fetch_end, today)
            if tail_end > fetch_end and _latest_price_date(prices) < target_date:
                tail_prices = client.fetch_daily_prices(sid, fetch_start, tail_end)
                price_warnings = _dedupe_texts([*price_warnings, *list(getattr(client, "last_warnings", []))])
                prices = _merge_daily_prices(prices, tail_prices)
            price_rows = 0
            if prices:
                price_rows = store.upsert_daily_prices(prices)
            coverage_after_raw = store.refresh_data_coverage(
                sid,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
            )
            post_status = resolve_post_patch_status(
                gap_plan,
                latest_date=coverage_after_raw.get("latest_date"),
                rows_written=price_rows,
            )
            store.refresh_data_coverage(
                sid,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
                status=post_status.status,
                suspect_reason=post_status.reason if post_status.status != STATUS_PATCHED else "",
            )
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
        elif price_warnings:
            have = latest[-1].date.isoformat() if latest else "無資料"
            error = _bulk_unstable_source_error(sid, have, target_date, price_warnings)
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "failed", error=error)
            raise RuntimeError(error)
        elif _is_short_source_pending(gap_plan, post_status):
            have = latest[-1].date.isoformat() if latest else "無資料"
            store.mark_bulk_item(
                BULK_RUN_KEY,
                "stock",
                sid,
                BULK_STATUS_SOURCE_PENDING,
                error=(
                    f"日線暫時只到 {have}，目標={target_date.isoformat()}；"
                    "可能是最新交易日尚未公布或該檔當日無交易，稍後再重試。"
                ),
            )
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
        if _bulk_failed_backoff_until(ctx, sid) is not None:
            return True
        # 重點修正：不再用 bulk_progress 的 "done" 短路。
        # 舊版只要曾標 done 就永遠跳過 → 過期股票即使重按全市場下載也補不回來。
        # 同時不可只看最新日期：STOCK_DAY_ALL top-up 可能只補到最新幾筆，
        # 這種「假最新」仍要回補歷史（plan_data_gap 內用 depth 軸判定，
        # 期望筆數由上市日 + 交易日曆推導，頂到 target 也擋不住深度不足）。
        coverage = store.refresh_data_coverage(
            sid,
            DATA_NODE_DAILY_PRICE,
            target_date=target_date,
        )
        gap_plan = plan_data_gap(
            stock_id=sid,
            node=DATA_NODE_DAILY_PRICE,
            coverage=coverage,
            target_date=target_date,
            lookback_days=lookback_days,
            max_patch_business_days=45,
            listed_date=_listed_date_for(ctx, sid),
        )
        if gap_plan.status == STATUS_CURRENT:
            store.mark_bulk_item(BULK_RUN_KEY, "stock", sid, "done")
            return True
        return False

    def on_finish(_status) -> None:
        store = ctx.get("store")
        client = ctx.get("client")
        # 1) 收尾再跑一次全市場最新日線 top-up：長時間下載期間來源可能更新。
        #    全市場下載採「最新日優先」；個別歷史不足留給看個股 / 補這檔時再補。
        if client is not None and store is not None and not retry_failed_only:
            _top_up_latest_all_prices(store, client)
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


def _listed_date_for(ctx: dict, stock_id: str) -> date | None:
    """先查 prelude 建的 map；retry_failed_only 沒跑清單 → 退回 store 的 profile。"""
    listed = (ctx.get("listed_dates") or {}).get(stock_id)
    if listed is not None:
        return listed
    store = ctx.get("store")
    getter = getattr(store, "get_profile", None)
    if getter is None:
        return None
    try:
        profile = getter(stock_id)
    except Exception:  # noqa: BLE001 - 查不到上市日就退回無 clamp 的原行為
        return None
    return getattr(profile, "listed_date", None) if profile is not None else None


def _prioritized_stock_ids(
    ctx: dict,
    stock_ids: list[str],
    target_date: date,
    lookback_days: int,
) -> list[str]:
    store = ctx.get("store")
    if store is None:
        return list(stock_ids)

    def key_for(sid: str) -> tuple[int, int, str]:
        if _bulk_failed_backoff_until(ctx, sid) is not None:
            return (6, 0, sid)
        try:
            coverage = store.refresh_data_coverage(
                sid,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
            )
            plan = plan_data_gap(
                stock_id=sid,
                node=DATA_NODE_DAILY_PRICE,
                coverage=coverage,
                target_date=target_date,
                lookback_days=lookback_days,
                max_patch_business_days=45,
                listed_date=_listed_date_for(ctx, sid),
            )
        except Exception:  # noqa: BLE001 - 單檔排序失敗不應阻斷整批下載
            return (8, 0, sid)
        return _bulk_stock_priority_key(plan, sid)

    return sorted((str(sid) for sid in stock_ids), key=key_for)


def _bulk_stock_priority_key(plan, stock_id: str) -> tuple[int, int, str]:
    """讓小缺口先跑，避免只差一天的股票排在大量歷史回補後面。"""
    if plan.status == STATUS_CURRENT:
        return (9, 0, stock_id)
    if plan.status == STATUS_SOURCE_PENDING:
        return (7, 0, stock_id)
    if plan.can_patch:
        if plan.local_latest_date is None:
            return (4, int(plan.gap_business_days or 0), stock_id)
        return (0, int(plan.gap_business_days or 0), stock_id)
    if plan.local_latest_date is not None and plan.target_date is not None:
        if plan.local_latest_date >= plan.target_date:
            return (3, int(plan.gap_business_days or 0), stock_id)
        return (2, int(plan.gap_business_days or 0), stock_id)
    return (5, int(plan.gap_business_days or 0), stock_id)


def _bulk_failed_backoff_until(ctx: dict, stock_id: str) -> datetime | None:
    store = ctx.get("store")
    getter = getattr(store, "get_bulk_item", None)
    if getter is None:
        return None
    try:
        item = getter(BULK_RUN_KEY, "stock", stock_id)
    except Exception:  # noqa: BLE001
        return None
    if not item or item.get("status") != "failed":
        return None
    updated_at = item.get("updated_at")
    if not updated_at:
        return None
    try:
        retry_at = datetime.fromisoformat(str(updated_at)) + timedelta(
            seconds=BULK_FAILED_RETRY_BACKOFF_SECONDS
        )
    except ValueError:
        return None
    return retry_at if retry_at > datetime.now() else None


def _latest_price_date(prices: list[DailyPrice]) -> date:
    if not prices:
        return date.min
    return max(price.date for price in prices)


def _merge_daily_prices(*groups: list[DailyPrice]) -> list[DailyPrice]:
    by_key: dict[tuple[str, date], DailyPrice] = {}
    for group in groups:
        for price in group:
            by_key[(price.stock_id, price.date)] = price
    return sorted(by_key.values(), key=lambda item: (item.stock_id, item.date))


def _top_up_latest_all_prices(store, client) -> None:
    try:
        latest_all = client.fetch_latest_all_prices()
        if latest_all:
            store.upsert_daily_prices(latest_all)
            if hasattr(store, "delete_json_cache"):
                store.delete_json_cache("local_data_v2")
    except Exception:  # noqa: BLE001 - 安全網失敗不影響主流程
        pass


def _dedupe_texts(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _bulk_unstable_source_error(
    stock_id: str,
    latest_date_text: str,
    target_date: date,
    warnings: list[str],
) -> str:
    first = warnings[0] if warnings else "TWSE 暫時沒有回應"
    return (
        f"TWSE 抓取不穩，{stock_id} 日線未補齊"
        f"（最後={latest_date_text}，目標={target_date.isoformat()}）。"
        f"已先停止硬補；稍後按重試失敗。首個警告：{first}"
    )


def _is_short_source_pending(gap_plan, post_status) -> bool:
    if post_status is None or post_status.status != STATUS_SOURCE_PENDING:
        return False
    return 0 <= int(getattr(gap_plan, "gap_business_days", 0) or 0) <= 2
