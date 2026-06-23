from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.analyze.dividends import dedupe_dividend_records as _dedupe_dividend_records
from app.analyze.data_gap import (
    DATA_NODE_DAILY_PRICE,
    DATA_NODE_INSTITUTIONAL,
    STATUS_CURRENT,
    plan_data_gap,
    previous_business_day,
    resolve_post_patch_status,
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
        )
        if gap_plan.status == STATUS_CURRENT:
            message = gap_plan.reason
            self.store.record_sync_run(
                kind="stock_history",
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

        start_date = gap_plan.fetch_start_date or (target_date - timedelta(days=lookback_days))
        fetch_end_date = gap_plan.fetch_end_date or target_date
        rows_written = 0
        status = "success"
        message = ""

        try:
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
                    dividends.extend(
                        self.client.fetch_historical_dividend_records(
                            stock_id,
                            start_date,
                            fetch_end_date,
                        )
                    )
                    dividend_warnings.extend(getattr(self.client, "last_warnings", [])[warning_count:])
                except Exception as exc:
                    dividend_warnings.append(f"Skipped historical dividends: {exc}")
            dividends = _dedupe_dividend_records(dividends)
            dividend_rows = self.store.upsert_dividend_records(dividends)

            prices = self.client.fetch_daily_prices(stock_id, start_date, fetch_end_date)
            price_warnings = list(getattr(self.client, "last_warnings", []))
            price_rows = self.store.upsert_daily_prices(prices)
            rows_written = price_rows
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
            valuation = self.client.fetch_market_valuation(stock_id)
            valuation_rows = self.store.upsert_market_valuations([valuation]) if valuation else 0
            revenue = self.client.fetch_monthly_revenue(stock_id)
            revenue_rows = self.store.upsert_monthly_revenues([revenue]) if revenue else 0
            financial = self.client.fetch_financial_statement(stock_id)
            financial_rows = self.store.upsert_financial_statements([financial]) if financial else 0
            rows_written += dividend_rows + valuation_rows + revenue_rows + financial_rows
            warning_parts = []
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
                f"{dividend_rows} dividends, "
                f"{valuation_rows} valuation, {revenue_rows} revenue, "
                f"{financial_rows} financial). Data gap: {gap_plan.reason} "
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
