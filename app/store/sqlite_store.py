from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    InstitutionalTrade,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.portfolio.models import PortfolioTransaction


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stock_profiles (
    stock_id TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    industry_code TEXT,
    listed_date TEXT,
    source_updated_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_prices (
    stock_id TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    trade_value INTEGER,
    transaction_count INTEGER,
    change REAL,
    note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_stock_date
    ON daily_prices(stock_id, date);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_written INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    stock_id TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dividend_records (
    stock_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    period TEXT NOT NULL,
    status TEXT NOT NULL,
    board_date TEXT,
    shareholder_meeting_date TEXT,
    cash_dividend REAL NOT NULL,
    stock_dividend REAL NOT NULL,
    source_updated_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, year, period)
);

CREATE INDEX IF NOT EXISTS idx_dividend_records_stock_year
    ON dividend_records(stock_id, year DESC);

CREATE TABLE IF NOT EXISTS market_valuations (
    stock_id TEXT NOT NULL,
    date TEXT NOT NULL,
    pe_ratio REAL,
    dividend_yield REAL,
    pb_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, date)
);

CREATE INDEX IF NOT EXISTS idx_market_valuations_stock_date
    ON market_valuations(stock_id, date DESC);

CREATE TABLE IF NOT EXISTS monthly_revenues (
    stock_id TEXT NOT NULL,
    year_month TEXT NOT NULL,
    company_name TEXT NOT NULL,
    industry TEXT NOT NULL,
    current_month_revenue INTEGER NOT NULL,
    previous_month_revenue INTEGER,
    last_year_month_revenue INTEGER,
    mom_percent REAL,
    yoy_percent REAL,
    cumulative_revenue INTEGER,
    cumulative_last_year_revenue INTEGER,
    cumulative_yoy_percent REAL,
    source_updated_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, year_month)
);

CREATE INDEX IF NOT EXISTS idx_monthly_revenues_stock_month
    ON monthly_revenues(stock_id, year_month DESC);

CREATE TABLE IF NOT EXISTS financial_statements (
    stock_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    company_name TEXT NOT NULL,
    revenue INTEGER,
    gross_profit INTEGER,
    operating_income INTEGER,
    non_operating_income_expense INTEGER,
    pre_tax_income INTEGER,
    net_income INTEGER,
    parent_net_income INTEGER,
    eps REAL,
    total_assets INTEGER,
    total_liabilities INTEGER,
    parent_equity INTEGER,
    total_equity INTEGER,
    book_value_per_share REAL,
    source_updated_at TEXT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, year, quarter)
);

CREATE INDEX IF NOT EXISTS idx_financial_statements_stock_period
    ON financial_statements(stock_id, year DESC, quarter DESC);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    shares INTEGER NOT NULL CHECK(shares > 0),
    price REAL NOT NULL CHECK(price >= 0),
    fee REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_stock_date
    ON portfolio_transactions(stock_id, trade_date, id);

CREATE TABLE IF NOT EXISTS institutional_trades (
    stock_id TEXT NOT NULL,
    date TEXT NOT NULL,
    foreign_net INTEGER NOT NULL DEFAULT 0,
    trust_net INTEGER NOT NULL DEFAULT 0,
    dealer_net INTEGER NOT NULL DEFAULT 0,
    total_net INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, date)
);

CREATE INDEX IF NOT EXISTS idx_institutional_trades_stock_date
    ON institutional_trades(stock_id, date);
"""


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def ensure_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def upsert_profiles(self, profiles: Iterable[StockProfile]) -> int:
        rows = list(profiles)
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO stock_profiles (
                stock_id, market, name, short_name, industry_code,
                listed_date, source_updated_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id) DO UPDATE SET
                market = excluded.market,
                name = excluded.name,
                short_name = excluded.short_name,
                industry_code = excluded.industry_code,
                listed_date = excluded.listed_date,
                source_updated_at = excluded.source_updated_at,
                updated_at = excluded.updated_at
            """,
            [
                (
                    item.stock_id,
                    item.market,
                    item.name,
                    item.short_name,
                    item.industry_code,
                    _d(item.listed_date),
                    _d(item.source_updated_at),
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def upsert_daily_prices(self, prices: Iterable[DailyPrice]) -> int:
        rows = list(prices)
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO daily_prices (
                stock_id, date, open, high, low, close, volume, trade_value,
                transaction_count, change, note, source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                trade_value = excluded.trade_value,
                transaction_count = excluded.transaction_count,
                change = excluded.change,
                note = excluded.note,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    _d(item.date),
                    item.open,
                    item.high,
                    item.low,
                    item.close,
                    item.volume,
                    item.trade_value,
                    item.transaction_count,
                    item.change,
                    item.note,
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def upsert_dividend_records(self, records: Iterable[DividendRecord]) -> int:
        rows = list(records)
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO dividend_records (
                stock_id, year, period, status, board_date,
                shareholder_meeting_date, cash_dividend, stock_dividend,
                source_updated_at, note, source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, year, period) DO UPDATE SET
                status = excluded.status,
                board_date = excluded.board_date,
                shareholder_meeting_date = excluded.shareholder_meeting_date,
                cash_dividend = excluded.cash_dividend,
                stock_dividend = excluded.stock_dividend,
                source_updated_at = excluded.source_updated_at,
                note = excluded.note,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    item.year,
                    item.period,
                    item.status,
                    _d(item.board_date),
                    _d(item.shareholder_meeting_date),
                    item.cash_dividend,
                    item.stock_dividend,
                    _d(item.source_updated_at),
                    item.note,
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def replace_dividend_records(self, stock_id: str, records: Iterable[DividendRecord]) -> int:
        rows = list(records)
        self.conn.execute("DELETE FROM dividend_records WHERE stock_id = ?", (stock_id,))
        self.conn.commit()
        return self.upsert_dividend_records(rows)

    def upsert_market_valuations(self, valuations: Iterable[MarketValuation | None]) -> int:
        rows = [item for item in valuations if item is not None]
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO market_valuations (
                stock_id, date, pe_ratio, dividend_yield, pb_ratio, source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                pe_ratio = excluded.pe_ratio,
                dividend_yield = excluded.dividend_yield,
                pb_ratio = excluded.pb_ratio,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    _d(item.date),
                    item.pe_ratio,
                    item.dividend_yield,
                    item.pb_ratio,
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def upsert_monthly_revenues(self, revenues: Iterable[MonthlyRevenue | None]) -> int:
        rows = [item for item in revenues if item is not None]
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO monthly_revenues (
                stock_id, year_month, company_name, industry,
                current_month_revenue, previous_month_revenue,
                last_year_month_revenue, mom_percent, yoy_percent,
                cumulative_revenue, cumulative_last_year_revenue,
                cumulative_yoy_percent, source_updated_at, note, source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, year_month) DO UPDATE SET
                company_name = excluded.company_name,
                industry = excluded.industry,
                current_month_revenue = excluded.current_month_revenue,
                previous_month_revenue = excluded.previous_month_revenue,
                last_year_month_revenue = excluded.last_year_month_revenue,
                mom_percent = excluded.mom_percent,
                yoy_percent = excluded.yoy_percent,
                cumulative_revenue = excluded.cumulative_revenue,
                cumulative_last_year_revenue = excluded.cumulative_last_year_revenue,
                cumulative_yoy_percent = excluded.cumulative_yoy_percent,
                source_updated_at = excluded.source_updated_at,
                note = excluded.note,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    item.year_month,
                    item.company_name,
                    item.industry,
                    item.current_month_revenue,
                    item.previous_month_revenue,
                    item.last_year_month_revenue,
                    item.mom_percent,
                    item.yoy_percent,
                    item.cumulative_revenue,
                    item.cumulative_last_year_revenue,
                    item.cumulative_yoy_percent,
                    _d(item.source_updated_at),
                    item.note,
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def upsert_financial_statements(self, statements: Iterable[FinancialStatement | None]) -> int:
        rows = [item for item in statements if item is not None]
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO financial_statements (
                stock_id, year, quarter, company_name, revenue, gross_profit,
                operating_income, non_operating_income_expense, pre_tax_income,
                net_income, parent_net_income, eps, total_assets, total_liabilities,
                parent_equity, total_equity, book_value_per_share, source_updated_at,
                source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, year, quarter) DO UPDATE SET
                company_name = excluded.company_name,
                revenue = excluded.revenue,
                gross_profit = excluded.gross_profit,
                operating_income = excluded.operating_income,
                non_operating_income_expense = excluded.non_operating_income_expense,
                pre_tax_income = excluded.pre_tax_income,
                net_income = excluded.net_income,
                parent_net_income = excluded.parent_net_income,
                eps = excluded.eps,
                total_assets = excluded.total_assets,
                total_liabilities = excluded.total_liabilities,
                parent_equity = excluded.parent_equity,
                total_equity = excluded.total_equity,
                book_value_per_share = excluded.book_value_per_share,
                source_updated_at = excluded.source_updated_at,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    item.year,
                    item.quarter,
                    item.company_name,
                    item.revenue,
                    item.gross_profit,
                    item.operating_income,
                    item.non_operating_income_expense,
                    item.pre_tax_income,
                    item.net_income,
                    item.parent_net_income,
                    item.eps,
                    item.total_assets,
                    item.total_liabilities,
                    item.parent_equity,
                    item.total_equity,
                    item.book_value_per_share,
                    _d(item.source_updated_at),
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def get_profile(self, stock_id: str) -> StockProfile | None:
        row = self.conn.execute(
            """
            SELECT stock_id, market, name, short_name, industry_code,
                   listed_date, source_updated_at
            FROM stock_profiles
            WHERE stock_id = ?
            """,
            (stock_id,),
        ).fetchone()
        if row is None:
            return None
        return _profile_from_row(row)

    def search_profiles(self, query: str, *, limit: int = 20) -> list[StockProfile]:
        needle = f"%{query.strip()}%"
        rows = self.conn.execute(
            """
            SELECT stock_id, market, name, short_name, industry_code,
                   listed_date, source_updated_at
            FROM stock_profiles
            WHERE stock_id LIKE ?
               OR name LIKE ?
               OR short_name LIKE ?
            ORDER BY stock_id
            LIMIT ?
            """,
            (needle, needle, needle, limit),
        ).fetchall()
        return [_profile_from_row(row) for row in rows]

    def get_daily_prices(
        self,
        stock_id: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[DailyPrice]:
        clauses = ["stock_id = ?"]
        params: list[object] = [stock_id]
        if start_date is not None:
            clauses.append("date >= ?")
            params.append(_d(start_date))
        if end_date is not None:
            clauses.append("date <= ?")
            params.append(_d(end_date))

        sql = f"""
            SELECT stock_id, date, open, high, low, close, volume, trade_value,
                   transaction_count, change, note, source
            FROM daily_prices
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        prices = [_price_from_row(row) for row in rows]
        return list(reversed(prices))

    def upsert_institutional_trades(self, trades: Iterable[InstitutionalTrade]) -> int:
        rows = list(trades)
        now = _dt(datetime.now())
        self.conn.executemany(
            """
            INSERT INTO institutional_trades (
                stock_id, date, foreign_net, trust_net, dealer_net, total_net,
                source, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(stock_id, date) DO UPDATE SET
                foreign_net = excluded.foreign_net,
                trust_net = excluded.trust_net,
                dealer_net = excluded.dealer_net,
                total_net = excluded.total_net,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            [
                (
                    item.stock_id,
                    _d(item.date),
                    int(item.foreign_net),
                    int(item.trust_net),
                    int(item.dealer_net),
                    int(item.total_net),
                    item.source,
                    now,
                )
                for item in rows
            ],
        )
        self.conn.commit()
        return len(rows)

    def get_institutional_stock_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT DISTINCT stock_id FROM institutional_trades").fetchall()
        return {row["stock_id"] for row in rows}

    def get_institutional_dates_any(self) -> set[str]:
        rows = self.conn.execute("SELECT DISTINCT date FROM institutional_trades").fetchall()
        return {row["date"] for row in rows}

    def get_institutional_dates(self, stock_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT date FROM institutional_trades WHERE stock_id = ?",
            (stock_id,),
        ).fetchall()
        return {row["date"] for row in rows}

    def get_institutional_trades(
        self,
        stock_id: str,
        *,
        limit: int | None = None,
    ) -> list[InstitutionalTrade]:
        sql = """
            SELECT stock_id, date, foreign_net, trust_net, dealer_net, total_net, source
            FROM institutional_trades
            WHERE stock_id = ?
            ORDER BY date DESC
        """
        params: list[object] = [stock_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        trades = [
            InstitutionalTrade(
                stock_id=row["stock_id"],
                date=date.fromisoformat(row["date"]),
                foreign_net=int(row["foreign_net"]),
                trust_net=int(row["trust_net"]),
                dealer_net=int(row["dealer_net"]),
                total_net=int(row["total_net"]),
                source=row["source"],
            )
            for row in rows
        ]
        return list(reversed(trades))

    def get_dividend_records(self, stock_id: str, *, limit: int | None = None) -> list[DividendRecord]:
        sql = """
            SELECT stock_id, year, period, status, board_date,
                   shareholder_meeting_date, cash_dividend, stock_dividend,
                   source_updated_at, note, source
            FROM dividend_records
            WHERE stock_id = ?
            ORDER BY year DESC, period DESC
        """
        params: list[object] = [stock_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_dividend_from_row(row) for row in rows]

    def get_latest_market_valuation(self, stock_id: str) -> MarketValuation | None:
        row = self.conn.execute(
            """
            SELECT stock_id, date, pe_ratio, dividend_yield, pb_ratio, source
            FROM market_valuations
            WHERE stock_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (stock_id,),
        ).fetchone()
        if row is None:
            return None
        return _valuation_from_row(row)

    def get_monthly_revenues(self, stock_id: str, *, limit: int | None = None) -> list[MonthlyRevenue]:
        sql = """
            SELECT stock_id, year_month, company_name, industry,
                   current_month_revenue, previous_month_revenue,
                   last_year_month_revenue, mom_percent, yoy_percent,
                   cumulative_revenue, cumulative_last_year_revenue,
                   cumulative_yoy_percent, source_updated_at, note, source
            FROM monthly_revenues
            WHERE stock_id = ?
            ORDER BY year_month DESC
        """
        params: list[object] = [stock_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_monthly_revenue_from_row(row) for row in rows]

    def get_financial_statements(self, stock_id: str, *, limit: int | None = None) -> list[FinancialStatement]:
        sql = """
            SELECT stock_id, year, quarter, company_name, revenue, gross_profit,
                   operating_income, non_operating_income_expense, pre_tax_income,
                   net_income, parent_net_income, eps, total_assets, total_liabilities,
                   parent_equity, total_equity, book_value_per_share,
                   source_updated_at, source
            FROM financial_statements
            WHERE stock_id = ?
            ORDER BY year DESC, quarter DESC
        """
        params: list[object] = [stock_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_financial_statement_from_row(row) for row in rows]

    def get_latest_financial_statement(self, stock_id: str) -> FinancialStatement | None:
        rows = self.get_financial_statements(stock_id, limit=1)
        return rows[0] if rows else None

    def get_price_stock_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT DISTINCT stock_id FROM daily_prices").fetchall()
        return {row["stock_id"] for row in rows}

    def count_daily_prices(self, stock_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total FROM daily_prices WHERE stock_id = ?",
            (stock_id,),
        ).fetchone()
        return int(row["total"])

    def add_to_watchlist(self, stock_id: str, *, note: str = "") -> None:
        self.conn.execute(
            """
            INSERT INTO watchlist (stock_id, added_at, note)
            VALUES (?, ?, ?)
            ON CONFLICT(stock_id) DO UPDATE SET
                note = excluded.note
            """,
            (stock_id, _dt(datetime.now()), note),
        )
        self.conn.commit()

    def remove_from_watchlist(self, stock_id: str) -> None:
        self.conn.execute("DELETE FROM watchlist WHERE stock_id = ?", (stock_id,))
        self.conn.commit()

    def is_watchlisted(self, stock_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM watchlist WHERE stock_id = ?",
            (stock_id,),
        ).fetchone()
        return row is not None

    def list_watchlist(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT w.stock_id, w.added_at, w.note,
                   p.market, p.name, p.short_name, p.industry_code,
                   p.listed_date, p.source_updated_at
            FROM watchlist w
            LEFT JOIN stock_profiles p ON p.stock_id = w.stock_id
            ORDER BY w.added_at DESC
            """
        ).fetchall()

    def add_portfolio_transaction(self, transaction: PortfolioTransaction) -> int:
        now = _dt(datetime.now())
        cursor = self.conn.execute(
            """
            INSERT INTO portfolio_transactions (
                stock_id, trade_date, side, shares, price, fee, tax,
                note, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction.stock_id.strip(),
                _d(transaction.trade_date),
                transaction.side,
                transaction.shares,
                transaction.price,
                transaction.fee,
                transaction.tax,
                transaction.note,
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_portfolio_transaction(self, transaction: PortfolioTransaction) -> None:
        if transaction.id is None:
            raise ValueError("transaction id is required")
        cursor = self.conn.execute(
            """
            UPDATE portfolio_transactions
            SET stock_id = ?,
                trade_date = ?,
                side = ?,
                shares = ?,
                price = ?,
                fee = ?,
                tax = ?,
                note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                transaction.stock_id.strip(),
                _d(transaction.trade_date),
                transaction.side,
                transaction.shares,
                transaction.price,
                transaction.fee,
                transaction.tax,
                transaction.note,
                _dt(datetime.now()),
                transaction.id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"portfolio transaction {transaction.id} not found")
        self.conn.commit()

    def delete_portfolio_transaction(self, transaction_id: int) -> None:
        cursor = self.conn.execute(
            "DELETE FROM portfolio_transactions WHERE id = ?",
            (transaction_id,),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"portfolio transaction {transaction_id} not found")
        self.conn.commit()

    def get_portfolio_transactions(self) -> list[PortfolioTransaction]:
        rows = self.conn.execute(
            """
            SELECT id, stock_id, trade_date, side, shares, price, fee, tax,
                   note, created_at, updated_at
            FROM portfolio_transactions
            ORDER BY trade_date, id
            """
        ).fetchall()
        return [_portfolio_transaction_from_row(row) for row in rows]

    def record_sync_run(
        self,
        *,
        kind: str,
        target: str,
        status: str,
        rows_written: int,
        started_at: datetime,
        finished_at: datetime,
        message: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sync_runs (
                kind, target, status, rows_written, started_at, finished_at, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kind,
                target,
                status,
                rows_written,
                _dt(started_at),
                _dt(finished_at),
                message,
            ),
        )
        self.conn.commit()


def _profile_from_row(row: sqlite3.Row) -> StockProfile:
    return StockProfile(
        stock_id=row["stock_id"],
        market=row["market"],
        name=row["name"],
        short_name=row["short_name"],
        industry_code=row["industry_code"],
        listed_date=_date_or_none(row["listed_date"]),
        source_updated_at=_date_or_none(row["source_updated_at"]),
    )


def _price_from_row(row: sqlite3.Row) -> DailyPrice:
    return DailyPrice(
        stock_id=row["stock_id"],
        date=date.fromisoformat(row["date"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
        trade_value=row["trade_value"],
        transaction_count=row["transaction_count"],
        change=row["change"],
        note=row["note"],
        source=row["source"],
    )


def _dividend_from_row(row: sqlite3.Row) -> DividendRecord:
    return DividendRecord(
        stock_id=row["stock_id"],
        year=int(row["year"]),
        period=row["period"],
        status=row["status"],
        board_date=_date_or_none(row["board_date"]),
        shareholder_meeting_date=_date_or_none(row["shareholder_meeting_date"]),
        cash_dividend=float(row["cash_dividend"]),
        stock_dividend=float(row["stock_dividend"]),
        source_updated_at=_date_or_none(row["source_updated_at"]),
        note=row["note"],
        source=row["source"],
    )


def _valuation_from_row(row: sqlite3.Row) -> MarketValuation:
    return MarketValuation(
        stock_id=row["stock_id"],
        date=date.fromisoformat(row["date"]),
        pe_ratio=row["pe_ratio"],
        dividend_yield=row["dividend_yield"],
        pb_ratio=row["pb_ratio"],
        source=row["source"],
    )


def _monthly_revenue_from_row(row: sqlite3.Row) -> MonthlyRevenue:
    return MonthlyRevenue(
        stock_id=row["stock_id"],
        year_month=row["year_month"],
        company_name=row["company_name"],
        industry=row["industry"],
        current_month_revenue=int(row["current_month_revenue"]),
        previous_month_revenue=row["previous_month_revenue"],
        last_year_month_revenue=row["last_year_month_revenue"],
        mom_percent=row["mom_percent"],
        yoy_percent=row["yoy_percent"],
        cumulative_revenue=row["cumulative_revenue"],
        cumulative_last_year_revenue=row["cumulative_last_year_revenue"],
        cumulative_yoy_percent=row["cumulative_yoy_percent"],
        source_updated_at=_date_or_none(row["source_updated_at"]),
        note=row["note"],
        source=row["source"],
    )


def _financial_statement_from_row(row: sqlite3.Row) -> FinancialStatement:
    return FinancialStatement(
        stock_id=row["stock_id"],
        year=int(row["year"]),
        quarter=int(row["quarter"]),
        company_name=row["company_name"],
        revenue=row["revenue"],
        gross_profit=row["gross_profit"],
        operating_income=row["operating_income"],
        non_operating_income_expense=row["non_operating_income_expense"],
        pre_tax_income=row["pre_tax_income"],
        net_income=row["net_income"],
        parent_net_income=row["parent_net_income"],
        eps=row["eps"],
        total_assets=row["total_assets"],
        total_liabilities=row["total_liabilities"],
        parent_equity=row["parent_equity"],
        total_equity=row["total_equity"],
        book_value_per_share=row["book_value_per_share"],
        source_updated_at=_date_or_none(row["source_updated_at"]),
        source=row["source"],
    )


def _portfolio_transaction_from_row(row: sqlite3.Row) -> PortfolioTransaction:
    return PortfolioTransaction(
        id=int(row["id"]),
        stock_id=row["stock_id"],
        trade_date=date.fromisoformat(row["trade_date"]),
        side=row["side"],
        shares=int(row["shares"]),
        price=float(row["price"]),
        fee=float(row["fee"]),
        tax=float(row["tax"]),
        note=row["note"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _d(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _date_or_none(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
