from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.models import DividendRecord
from app.store.sqlite_store import SQLiteStore
from app.sync.twse import TwseClient


@dataclass(frozen=True, slots=True)
class SyncResult:
    stock_id: str
    rows_written: int
    started_at: datetime
    finished_at: datetime
    message: str


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
    ) -> SyncResult:
        stock_id = stock_id.strip()
        if not stock_id:
            raise ValueError("stock_id is required")
        if lookback_days < 1:
            raise ValueError("lookback_days must be positive")

        started_at = datetime.now()
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=lookback_days)
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
                            end_date,
                        )
                    )
                    dividend_warnings.extend(getattr(self.client, "last_warnings", [])[warning_count:])
                except Exception as exc:
                    dividend_warnings.append(f"Skipped historical dividends: {exc}")
            dividends = _dedupe_dividend_records(dividends)
            dividend_rows = self.store.replace_dividend_records(stock_id, dividends)

            prices = self.client.fetch_daily_prices(stock_id, start_date, end_date)
            price_warnings = list(getattr(self.client, "last_warnings", []))
            rows_written = self.store.upsert_daily_prices(prices)
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
                f"({len(prices)} prices, {dividend_rows} dividends, "
                f"{valuation_rows} valuation, {revenue_rows} revenue, "
                f"{financial_rows} financial).{warning_text}"
            )
            return SyncResult(
                stock_id=stock_id,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
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
    ) -> SyncResult:
        """單獨抓三大法人買賣超（近一年、增量）。與主同步分開，使用者要看才按。"""
        stock_id = stock_id.strip()
        if not stock_id:
            raise ValueError("stock_id is required")
        started_at = datetime.now()
        end_date = end_date or date.today()
        start_date = end_date - timedelta(days=max(1, lookback_days))
        rows_written = 0
        status = "success"
        message = ""
        try:
            if hasattr(self.client, "last_warnings"):
                self.client.last_warnings = []
            known_dates = self.store.get_institutional_dates(stock_id)
            trades = self.client.fetch_institutional_trades(
                stock_id, start_date, end_date, max_days=300, skip_dates=known_dates,
            )
            rows_written = self.store.upsert_institutional_trades(trades)
            warnings = list(getattr(self.client, "last_warnings", []))
            warn = f" Skipped {len(warnings)} day(s)." if warnings else ""
            message = f"Synced {rows_written} institutional day(s) for {stock_id}.{warn}"
            return SyncResult(
                stock_id=stock_id,
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(),
                message=message,
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


def _dedupe_dividend_records(records: list[DividendRecord]) -> list[DividendRecord]:
    ex_dividend_amounts_by_year: dict[tuple[str, int], list[float]] = {}
    for record in records:
        if record.source == "TWSE_TWT49U":
            ex_dividend_amounts_by_year.setdefault(
                (record.stock_id, record.year),
                [],
            ).append(record.cash_dividend)

    by_key: dict[tuple[str, int, str], DividendRecord] = {}
    for record in records:
        if record.source == "TWSE_T187AP45":
            paid_amounts = ex_dividend_amounts_by_year.get((record.stock_id, record.year), [])
            if any(abs(record.cash_dividend - paid_amount) < 0.01 for paid_amount in paid_amounts):
                continue
        key = (record.stock_id, record.year, record.period)
        current = by_key.get(key)
        if current is None or current.source == "TWSE_TWT49U":
            by_key[key] = record
    return sorted(by_key.values(), key=lambda item: (item.year, item.period), reverse=True)
