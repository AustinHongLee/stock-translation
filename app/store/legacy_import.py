"""舊資料偵測與「非破壞性」匯入。

情境：新版把資料改存到 LOCALAPPDATA。若使用者「先開過程式」(LOCALAPPDATA 已被種了空 DB)，
之後才把舊版的 exe 旁 data 放回來，runtime_paths.migrate_legacy_data 會因為「目標已存在」而跳過，
舊資料就吃不進去。這個模組提供：偵測「舊 DB 比現在的 DB 有更多資料」→ 由 UI 詢問使用者 →
同意後用 ATTACH + INSERT OR IGNORE 把舊資料『併入』現在的 DB（不覆蓋、不刪舊檔、不需重開）。

純標準庫 sqlite3；對 schema 漂移有容忍（只匯入兩邊都有的欄位）。
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

# 要匯入的「使用者資料表」白名單。刻意排除 app_cache（純快取）與 bulk_progress（下載進度狀態）。
IMPORTABLE_TABLES: tuple[str, ...] = (
    "stock_profiles",
    "daily_prices",
    "dividend_records",
    "market_valuations",
    "monthly_revenues",
    "financial_statements",
    "institutional_trades",
    "data_coverage",
    "watchlist",
    "portfolio_transactions",
    "chart_annotations",
    "indicator_prefs",
)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def count_daily_stocks(db_path: Path | str) -> int:
    """資料量指標：daily_prices 內不同股票數。讀不到/沒有表都回 0（不丟例外）。"""
    path = Path(db_path)
    if not path.is_file():
        return 0
    try:
        conn = _connect(path)
    except sqlite3.Error:
        return 0
    try:
        row = conn.execute("SELECT COUNT(DISTINCT stock_id) AS n FROM daily_prices").fetchone()
        return int(row["n"]) if row and row["n"] is not None else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def legacy_import_status(legacy_db: Path | str, current_db: Path | str) -> dict[str, object]:
    """是否該提示匯入：舊 DB 存在、與現用 DB 不同檔、且舊 DB 的股票數 > 現用。"""
    legacy = Path(legacy_db)
    current = Path(current_db)
    legacy_n = count_daily_stocks(legacy)
    current_n = count_daily_stocks(current)
    different_file = (not current.exists()) or (_safe_resolve(legacy) != _safe_resolve(current))
    available = bool(legacy.is_file() and different_file and legacy_n > current_n)
    return {
        "available": available,
        "legacy_stock_count": legacy_n,
        "current_stock_count": current_n,
    }


def _safe_resolve(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _table_exists(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA {schema}.table_info("{table}")').fetchall()
    return [str(r["name"]) for r in rows]


def import_legacy_data(legacy_db: Path | str, current_db: Path | str) -> dict[str, object]:
    """把 legacy DB 的使用者資料 INSERT OR IGNORE 併入 current DB（非破壞性）。

    回傳 {"imported": {table: added_rows}, "tables": n, "rows": total}。
    """
    legacy = Path(legacy_db)
    current = Path(current_db)
    summary: dict[str, object] = {"imported": {}, "tables": 0, "rows": 0}
    if not legacy.is_file():
        return summary

    current.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(current)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("ATTACH DATABASE ? AS legacy", (str(legacy),))
        try:
            for table in IMPORTABLE_TABLES:
                if not _table_exists(conn, "main", table) or not _table_exists(conn, "legacy", table):
                    continue
                main_cols = _table_columns(conn, "main", table)
                legacy_cols = set(_table_columns(conn, "legacy", table))
                cols = [c for c in main_cols if c in legacy_cols]
                if not cols:
                    continue
                col_list = ", ".join(f'"{c}"' for c in cols)
                before = int(conn.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0])
                conn.execute(
                    f'INSERT OR IGNORE INTO main."{table}" ({col_list}) '
                    f'SELECT {col_list} FROM legacy."{table}"'
                )
                after = int(conn.execute(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0])
                added = after - before
                if added > 0:
                    imported = summary["imported"]
                    assert isinstance(imported, dict)
                    imported[table] = added
                    summary["rows"] = int(summary["rows"]) + added
                    summary["tables"] = int(summary["tables"]) + 1
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE legacy")
    finally:
        conn.close()
    return summary


def copy_legacy_snapshot(
    legacy_dir: Path | str,
    current_dir: Path | str,
    *,
    filename: str = "value_screener.json",
) -> bool:
    """把舊的雷達快照檔複製到新資料夾（使用者主動匯入時呼叫）。"""
    source = Path(legacy_dir) / filename
    if not source.is_file():
        return False
    target_dir = Path(current_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target_dir / filename)
        return True
    except OSError:
        return False
