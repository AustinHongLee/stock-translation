from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION

DEFAULT_OUTPUT_DIR = ROOT / "dist" / "seed"
SEED_TABLES = (
    "stock_profiles",
    "daily_prices",
    "dividend_records",
    "market_valuations",
    "monthly_revenues",
    "financial_statements",
    "institutional_trades",
    "data_coverage",
)
PRIVATE_TABLES = (
    "watchlist",
    "portfolio_transactions",
    "chart_annotations",
    "indicator_prefs",
    "app_cache",
    "bulk_progress",
)


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description="Build the bundled public seed data package.")
    parser.add_argument("--source", type=Path, default=_default_source_db())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=370)
    args = parser.parse_args()

    source = args.source.resolve()
    output_dir = args.output_dir.resolve()
    if not source.is_file():
        raise SystemExit(f"Source DB not found: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    seed_db = output_dir / "seed.sqlite3"
    tmp_db = output_dir / "seed.sqlite3.tmp"
    manifest_path = output_dir / "manifest.json"

    if tmp_db.exists():
        tmp_db.unlink()
    shutil.copy2(source, tmp_db)
    cutoff = date.today() - timedelta(days=max(1, int(args.days)))
    _trim_seed_db(tmp_db, cutoff=cutoff.isoformat())
    if seed_db.exists():
        seed_db.unlink()
    tmp_db.replace(seed_db)

    digest = _sha256(seed_db)
    manifest = {
        "data_snapshot_version": int(date.today().strftime("%Y%m%d")),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app_min_version": APP_VERSION,
        "sha256": digest,
        "tables": _table_stats(seed_db),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Source DB: {source}")
    print(f"Seed DB: {seed_db}")
    print(f"Manifest: {manifest_path}")
    print(f"sha256: {digest}")
    return 0


def _default_source_db() -> Path:
    try:
        raw = os.environ.get("STOCK_TRANSLATOR_SEED_SOURCE", "")
        if raw:
            return Path(raw)
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidate = Path(local_app_data) / "StockTranslator" / "data" / "stock_translator.sqlite3"
            if candidate.is_file():
                return candidate
    except OSError:
        pass
    return ROOT / "data" / "stock_translator.sqlite3"


def _trim_seed_db(path: Path, *, cutoff: str) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for table in PRIVATE_TABLES:
            if _table_exists(conn, table):
                conn.execute(f'DELETE FROM "{table}"')
        for table in ("daily_prices", "institutional_trades", "market_valuations"):
            if _table_exists(conn, table) and _column_exists(conn, table, "date"):
                conn.execute(f'DELETE FROM "{table}" WHERE date < ?', (cutoff,))
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def _table_stats(path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    stats: dict[str, dict[str, object]] = {}
    try:
        for table in SEED_TABLES:
            if not _table_exists(conn, table):
                continue
            table_stats: dict[str, object] = {
                "rows": int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]),
            }
            columns = _columns(conn, table)
            if "date" in columns:
                row = conn.execute(f'SELECT MIN(date) AS date_min, MAX(date) AS date_max FROM "{table}"').fetchone()
                table_stats["date_min"] = row["date_min"]
                table_stats["date_max"] = row["date_max"]
            if "year_month" in columns:
                row = conn.execute(
                    f'SELECT MIN(year_month) AS date_min, MAX(year_month) AS date_max FROM "{table}"'
                ).fetchone()
                table_stats["date_min"] = row["date_min"]
                table_stats["date_max"] = row["date_max"]
            if "stock_id" in columns:
                table_stats["stocks"] = int(
                    conn.execute(f'SELECT COUNT(DISTINCT stock_id) FROM "{table}"').fetchone()[0]
                )
            stats[table] = table_stats
    finally:
        conn.close()
    return stats


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in _columns(conn, table)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row[1]) for row in rows}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
