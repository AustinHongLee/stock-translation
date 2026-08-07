from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.version import APP_VERSION

DEFAULT_OUTPUT_DIR = ROOT / "dist" / "official_data"
DATA_FILES = ("stock_catalog.json", "value_screener.json")
PRIVATE_TABLES = (
    "watchlist",
    "price_alerts",
    "portfolio_transactions",
    "chart_annotations",
    "indicator_prefs",
    "app_cache",
    "bulk_progress",
)
TABLES_TO_REPORT = (
    "stock_profiles",
    "daily_prices",
    "dividend_records",
    "market_valuations",
    "monthly_revenues",
    "financial_statements",
    "institutional_trades",
    "data_coverage",
)


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description="Build the force-installable official DATA package.")
    parser.add_argument("--source", type=Path, default=_default_source_db())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--app-min-version",
        default="",
        help=(
            "覆寫 manifest 的 app_min_version（預設用 repo 目前 APP_VERSION）。"
            "每日自動資料包用它傳承上一包的版本閘，避免 main 分支版本超前把舊 app 鎖在門外。"
        ),
    )
    args = parser.parse_args()

    manifest = build_pack(
        args.source.resolve(),
        args.output_dir.resolve(),
        app_min_version=args.app_min_version.strip() or None,
    )
    print(f"Source DB: {Path(manifest['source_db'])}")
    print(f"Official DATA: {Path(manifest['output_dir'])}")
    print(f"sha256: {manifest['files']['data/stock_translator.sqlite3']['sha256']}")
    return 0


def build_pack(
    source_db: Path,
    output_dir: Path,
    *,
    app_min_version: str | None = None,
) -> dict[str, Any]:
    if not source_db.is_file():
        raise SystemExit(f"Source DB not found: {source_db}")

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target_db = data_dir / "stock_translator.sqlite3"
    tmp_db = data_dir / "stock_translator.sqlite3.tmp"
    if tmp_db.exists():
        tmp_db.unlink()

    shutil.copy2(source_db, tmp_db)
    _sanitize_db(tmp_db)
    if target_db.exists():
        target_db.unlink()
    tmp_db.replace(target_db)

    copied_files = _copy_data_files(source_db.parent, data_dir)
    files = _file_manifest(output_dir, [target_db, *copied_files])
    manifest: dict[str, Any] = {
        "data_snapshot_version": int(date.today().strftime("%Y%m%d")),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "app_min_version": app_min_version or APP_VERSION,
        "source_db": str(source_db),
        "output_dir": str(output_dir),
        "files": files,
        "tables": _table_stats(target_db),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _default_source_db() -> Path:
    raw = os.environ.get("STOCK_TRANSLATOR_DATA_PACK_SOURCE", "")
    if raw:
        return Path(raw)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "StockTranslator" / "data" / "stock_translator.sqlite3"
        if candidate.is_file():
            return candidate
    return ROOT / "data" / "stock_translator.sqlite3"


def _sanitize_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for table in PRIVATE_TABLES:
            if _table_exists(conn, table):
                conn.execute(f'DELETE FROM "{table}"')
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def _copy_data_files(source_dir: Path, output_data_dir: Path) -> list[Path]:
    copied: list[Path] = []
    for filename in DATA_FILES:
        source = source_dir / filename
        if not source.is_file():
            source = ROOT / "data" / filename
        if source.is_file():
            target = output_data_dir / filename
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def _file_manifest(root: Path, paths: list[Path]) -> dict[str, dict[str, object]]:
    return {
        path.relative_to(root).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(paths)
    }


def _table_stats(path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    stats: dict[str, dict[str, object]] = {}
    try:
        for table in TABLES_TO_REPORT:
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
