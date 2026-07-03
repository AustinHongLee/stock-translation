from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.analyze.dividends import (
    dedupe_dividend_records as _dedupe_dividend_records,
    dividend_history_start_date,
)
from app.analyze.data_gap import (
    DATA_NODE_DAILY_PRICE,
    DATA_NODE_INSTITUTIONAL,
    STATUS_CURRENT,
    plan_data_gap,
    previous_business_day,
    resolve_post_patch_status,
    same_month_tail_date,
)
from app.store.sqlite_store import SQLiteStore
from app.sync.twse import TwseClient


@dataclass(frozen=True, slots=True)
class SyncResult:
    stock_id: str
    rows_written: int
    started_at: datetime
    finished_at: datetime
    message: str
    skipped: bool = False
    gap_plan: dict[str, object] | None = None
    coverage: dict[str, object] | None = None
    post_status: dict[str, object] | None = None
    price_warning_count: int = 0
    first_price_warning: str = ""


class StockSyncService:
    def __init__(self, *, client: TwseClient, store: SQLiteStore) -> None:
        self.client = client
        self.store = store

    def sync_stock_history(
        self,
        stock_id: str,
        *,
        lookback_days: int = 365,
        end_date: date | None = None,
        target_date: date | None = None,
    ) -> SyncResult:
        stock_id = stock_id.strip()
        if not stock_id:
            raise ValueError("stock_id is required")
        if lookback_days < 1:
            raise ValueError("lookback_days must be positive")

        started_at = datetime.now()
        rows_written = 0
        status = "success"
        message = ""
        end_date = end_date or date.today()
        target_date = target_date or previous_business_day(end_date)
        coverage_before = self.store.refresh_data_coverage(
            stock_id,
            DATA_NODE_DAILY_PRICE,
            target_date=target_date,
        )
        gap_plan = plan_data_gap(
            stock_id=stock_id,
            node=DATA_NODE_DAILY_PRICE,
            coverage=coverage_before,
            target_date=target_date,
            lookback_days=lookback_days,
            max_patch_business_days=45,
            listed_date=_stored_listed_date(self.store, stock_id),
        )
        start_date = gap_plan.fetch_start_date or (target_date - timedelta(days=lookback_days))
        fetch_end_date = gap_plan.fetch_end_date or target_date

        try:
            metadata = self._refresh_stock_metadata(stock_id, fetch_end_date)
            rows_written += int(metadata["rows_written"])
            if gap_plan.status == STATUS_CURRENT:
                message = (
                    f"{gap_plan.reason} Price rows were skipped; refreshed metadata "
                    f"({metadata['dividend_rows']} dividends, {metadata['valuation_rows']} valuation, "
                    f"{metadata['revenue_rows']} revenue, {metadata['financial_rows']} financial)."
                )
                dividend_warnings = metadata["dividend_warnings"]
                if dividend_warnings:
                    message += (
                        f" Skipped {len(dividend_warnings)} dividend issue(s); "
                        f"first skipped: {dividend_warnings[0]}"
                    )
                return SyncResult(
                    stock_id=stock_id,
                    rows_written=rows_written,
                    started_at=started_at,
                    finished_at=datetime.now(),
                    message=message,
                    skipped=False,
                    gap_plan=gap_plan.to_json(),
                    coverage=coverage_before,
                    post_status={
                        "status": STATUS_CURRENT,
                        "reason": "Coverage was already current.",
                    },
                )

            if hasattr(self.client, "last_warnings"):
                self.client.last_warnings = []
            prices = self.client.fetch_daily_prices(stock_id, start_date, fetch_end_date)
            price_warnings = list(getattr(self.client, "last_warnings", []))
            tail_end_date = same_month_tail_date(fetch_end_date, end_date)
            if tail_end_date > fetch_end_date and _latest_price_date(prices) < target_date:
                retry_prices = self.client.fetch_daily_prices(stock_id, start_date, tail_end_date)
                retry_warnings = list(getattr(self.client, "last_warnings", []))
                prices = _merge_daily_prices(prices, retry_prices)
                price_warnings = _dedupe_texts([*price_warnings, *retry_warnings])
                fetch_end_date = tail_end_date
            price_rows = self.store.upsert_daily_prices(prices)
            rows_written += price_rows
            coverage_after_raw = self.store.refresh_data_coverage(
                stock_id,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
            )
            post_status = resolve_post_patch_status(
                gap_plan,
                latest_date=coverage_after_raw.get("latest_date"),
                rows_written=price_rows,
            )
            coverage_after = self.store.refresh_data_coverage(
                stock_id,
                DATA_NODE_DAILY_PRICE,
                target_date=target_date,
                status=post_status.status,
                suspect_reason=post_status.reason if post_status.status != "patched" else "",
            )
            warning_parts = []
            dividend_warnings = metadata["dividend_warnings"]
            if dividend_warnings:
                warning_parts.append(
                    f"Skipped {len(dividend_warnings)} dividend issue(s); "
                    f"first skipped: {dividend_warnings[0]}"
                )
            if price_warnings:
                warning_parts.append(
                    f"Skipped {len(price_warnings)} price month(s); "
                    f"first skipped: {price_warnings[0]}"
                )
            warning_text = f" {' '.join(warning_parts)}" if warning_parts else ""
            message = (
                f"Synced {rows_written} rows for {stock_id} "
                f"({len(prices)} prices from {start_date.isoformat()} to {fetch_end_date.isoformat()}, "
                f"{metadata['dividend_rows']} dividends, "
                f"{metadata['valuation_rows']} valuation, {metadata['revenue_rows']} revenue, "
                f"{metadata['financial_rows']} financial). Data gap: {gap_plan.reason} "
                f"Post-check: {post_status.reason}.{warning_text}"
            )
            return SyncResult(
                stock_id=stock_id,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
                gap_plan=gap_plan.to_json(),
                coverage=coverage_after,
                post_status=post_status.to_json(),
                price_warning_count=len(price_warnings),
                first_price_warning=price_warnings[0] if price_warnings else "",
            )
        except Exception as exc:
            status = "failed"
            message = str(exc)
            raise
        finally:
            self.store.record_sync_run(
                kind="stock_history",
                target=stock_id,
                status=status,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
            )

    def _refresh_stock_metadata(
        self,
        stock_id: str,
        fetch_end_date: date,
    ) -> dict[str, object]:
        profile = self.client.fetch_profile(stock_id)
        if profile is not None:
            self.store.upsert_profiles([profile])

        if hasattr(self.client, "last_warnings"):
            self.client.last_warnings = []
        dividend_warnings: list[str] = []
        dividends = list(self.client.fetch_dividend_records(stock_id))
        if hasattr(self.client, "fetch_historical_dividend_records"):
            try:
                warning_count = len(getattr(self.client, "last_warnings", []))
                dividend_start_date = dividend_history_start_date(fetch_end_date)
                dividends.extend(
                    self.client.fetch_historical_dividend_records(
                        stock_id,
                        dividend_start_date,
                        fetch_end_date,
                    )
                )
                dividend_warnings.extend(getattr(self.client, "last_warnings", [])[warning_count:])
            except Exception as exc:
                dividend_warnings.append(f"Skipped historical dividends: {exc}")
        dividends = _dedupe_dividend_records(dividends)
        dividend_rows = self.store.upsert_dividend_records(dividends)
        valuation = self.client.fetch_market_valuation(stock_id)
        valuation_rows = self.store.upsert_market_valuations([valuation]) if valuation else 0
        revenue = self.client.fetch_monthly_revenue(stock_id)
        revenue_rows = self.store.upsert_monthly_revenues([revenue]) if revenue else 0
        financial = self.client.fetch_financial_statement(stock_id)
        financial_rows = self.store.upsert_financial_statements([financial]) if financial else 0
        return {
            "rows_written": dividend_rows + valuation_rows + revenue_rows + financial_rows,
            "dividend_rows": dividend_rows,
            "valuation_rows": valuation_rows,
            "revenue_rows": revenue_rows,
            "financial_rows": financial_rows,
            "dividend_warnings": dividend_warnings,
        }


    def sync_institutional(
        self,
        stock_id: str,
        *,
        lookback_days: int = 365,
        end_date: date | None = None,
        target_date: date | None = None,
    ) -> SyncResult:
        """單獨抓三大法人買賣超（近一年、增量）。與主同步分開，使用者要看才按。"""
        stock_id = stock_id.strip()
        if not stock_id:
            raise ValueError("stock_id is required")
        started_at = datetime.now()
        end_date = end_date or date.today()
        target_date = target_date or previous_business_day(end_date)
        coverage_before = self.store.refresh_data_coverage(
            stock_id,
            DATA_NODE_INSTITUTIONAL,
            target_date=target_date,
        )
        gap_plan = plan_data_gap(
            stock_id=stock_id,
            node=DATA_NODE_INSTITUTIONAL,
            coverage=coverage_before,
            target_date=target_date,
            lookback_days=lookback_days,
            max_patch_business_days=60,
        )
        if gap_plan.status == STATUS_CURRENT:
            message = gap_plan.reason
            self.store.record_sync_run(
                kind="institutional",
                target=stock_id,
                status="skipped",
                rows_written=0,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
            )
            return SyncResult(
                stock_id=stock_id,
                rows_written=0,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
                skipped=True,
                gap_plan=gap_plan.to_json(),
                coverage=coverage_before,
            )

        start_date = gap_plan.fetch_start_date or (target_date - timedelta(days=max(1, lookback_days)))
        fetch_end_date = gap_plan.fetch_end_date or target_date
        rows_written = 0
        status = "success"
        message = ""
        try:
            if hasattr(self.client, "last_warnings"):
                self.client.last_warnings = []
            known_dates = self.store.get_institutional_dates(stock_id)
            max_days = max(20, gap_plan.gap_business_days + 5)
            trades = self.client.fetch_institutional_trades(
                stock_id, start_date, fetch_end_date, max_days=max_days, skip_dates=known_dates,
            )
            rows_written = self.store.upsert_institutional_trades(trades)
            coverage_after_raw = self.store.refresh_data_coverage(
                stock_id,
                DATA_NODE_INSTITUTIONAL,
                target_date=target_date,
            )
            post_status = resolve_post_patch_status(
                gap_plan,
                latest_date=coverage_after_raw.get("latest_date"),
                rows_written=rows_written,
            )
            coverage_after = self.store.refresh_data_coverage(
                stock_id,
                DATA_NODE_INSTITUTIONAL,
                target_date=target_date,
                status=post_status.status,
                suspect_reason=post_status.reason if post_status.status != "patched" else "",
            )
            warnings = list(getattr(self.client, "last_warnings", []))
            warn = f" Skipped {len(warnings)} day(s)." if warnings else ""
            message = (
                f"Synced {rows_written} institutional day(s) for {stock_id} "
                f"from {start_date.isoformat()} to {fetch_end_date.isoformat()}. "
                f"Data gap: {gap_plan.reason} Post-check: {post_status.reason}.{warn}"
            )
            return SyncResult(
                stock_id=stock_id,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
                gap_plan=gap_plan.to_json(),
                coverage=coverage_after,
            )
        except Exception as exc:
            status = "failed"
            message = str(exc)
            raise
        finally:
            self.store.record_sync_run(
                kind="institutional",
                target=stock_id,
                status=status,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
            )


def _stored_listed_date(store: SQLiteStore, stock_id: str) -> date | None:
    """從本地 profile 取上市日；第一次同步還沒有 profile 時回 None（維持原行為）。"""
    getter = getattr(store, "get_profile", None)
    if getter is None:
        return None
    try:
        profile = getter(stock_id)
    except Exception:  # noqa: BLE001
        return None
    return getattr(profile, "listed_date", None) if profile is not None else None


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


def _dedupe_texts(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result
