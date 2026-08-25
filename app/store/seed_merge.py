from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from app.analyze.data_gap import DATA_NODE_DAILY_PRICE, DATA_NODE_INSTITUTIONAL
from app.store.legacy_import import merge_sqlite
from app.store.sqlite_store import SQLiteStore
from app.update.checker import parse_version


SEED_DB_NAME = "seed.sqlite3"
OFFICIAL_DATA_DB_NAME = "data/stock_translator.sqlite3"
SEED_MANIFEST_NAME = "manifest.json"
SEED_APPLIED_CACHE_KEY = "seed_applied_version"
LOCAL_DATA_CACHE_KEY = "local_data_v3"

SEED_MERGE_TABLES: tuple[str, ...] = (
    "stock_profiles",
    "daily_prices",
    "dividend_records",
    "market_valuations",
    "monthly_revenues",
    "financial_statements",
    "institutional_trades",
    "data_coverage",
)


def read_seed_manifest(seed_directory: Path | str) -> dict[str, Any] | None:
    path = Path(seed_directory) / SEED_MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def applied_seed_version(store: SQLiteStore) -> int:
    cached = store.get_json_cache(SEED_APPLIED_CACHE_KEY)
    if cached is None:
        return 0
    payload, _updated_at = cached
    if isinstance(payload, int):
        return payload
    if isinstance(payload, dict):
        return _int_or_zero(payload.get("version"))
    return _int_or_zero(payload)


def set_applied_seed_version(store: SQLiteStore, version: int) -> None:
    store.set_json_cache(SEED_APPLIED_CACHE_KEY, {"version": int(version)})


def maybe_merge_seed(
    store: SQLiteStore,
    *,
    seed_dir: Path | str,
    current_db: Path | str,
    app_version: str,
    backups_dir: Path | str,
    force: bool = False,
) -> dict[str, Any]:
    """Merge bundled public seed data into the user's DB without overwriting rows.

    This must never block app startup with an exception. Any bad seed, old seed,
    hash mismatch, or SQLite failure returns a no-op payload instead.
    """
    try:
        seed_directory = Path(seed_dir)
        manifest = read_seed_manifest(seed_directory)
        if manifest is None:
            return {"applied": False, "reason": "missing_manifest"}

        seed_version = _int_or_zero(manifest.get("data_snapshot_version"))
        if seed_version <= 0:
            return {"applied": False, "reason": "invalid_manifest_version"}

        min_version = str(manifest.get("app_min_version") or "").strip()
        if min_version and not _app_version_allows(app_version, min_version):
            return {"applied": False, "reason": "app_too_old", "version": seed_version}

        current_applied = applied_seed_version(store)
        if not force and seed_version <= current_applied:
            return {
                "applied": False,
                "reason": "already_applied",
                "version": seed_version,
                "applied_version": current_applied,
            }

        seed_db, seed_db_key = _seed_db_candidate(seed_directory)
        if not seed_db.is_file():
            return {"applied": False, "reason": "missing_seed_db", "version": seed_version}

        expected_sha = _expected_seed_sha(manifest, seed_db_key)
        actual_sha = file_sha256(seed_db)
        if not expected_sha or actual_sha != expected_sha:
            return {
                "applied": False,
                "reason": "sha256_mismatch",
                "version": seed_version,
            }

        backup_path = _backup_current_db(Path(current_db), Path(backups_dir), seed_version)
        summary = merge_sqlite(seed_db, current_db, SEED_MERGE_TABLES)
        coverage_rows = _refresh_public_coverage(store)
        set_applied_seed_version(store, seed_version)
        store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
        return {
            "applied": True,
            "version": seed_version,
            "backup": str(backup_path) if backup_path else "",
            "coverage_rows": coverage_rows,
            **summary,
        }
    except Exception as exc:  # noqa: BLE001 - seed merge is best-effort and non-destructive
        return {"applied": False, "reason": "error", "error": str(exc)}


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_manifest_version(seed_directory: Path | str) -> int:
    manifest = read_seed_manifest(seed_directory)
    if manifest is None:
        return 0
    return _int_or_zero(manifest.get("data_snapshot_version"))


def _refresh_public_coverage(store: SQLiteStore) -> int:
    """資料包合併後以本機實際資料重算，不沿用包內可能過期的 coverage。"""
    stock_rows = store.conn.execute("SELECT stock_id FROM stock_profiles").fetchall()
    stock_ids = [str(row[0]) for row in stock_rows]
    refreshed = 0
    for node, table in (
        (DATA_NODE_DAILY_PRICE, "daily_prices"),
        (DATA_NODE_INSTITUTIONAL, "institutional_trades"),
    ):
        latest_row = store.conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()
        latest_text = str(latest_row[0] or "") if latest_row else ""
        if not latest_text:
            continue
        target_date = date.fromisoformat(latest_text)
        if node == DATA_NODE_INSTITUTIONAL:
            covered_rows = store.conn.execute(
                "SELECT DISTINCT stock_id FROM institutional_trades"
            ).fetchall()
            node_stock_ids = [str(row[0]) for row in covered_rows]
        else:
            node_stock_ids = stock_ids
        for stock_id in node_stock_ids:
            store.refresh_data_coverage(
                stock_id,
                node,
                target_date=target_date,
                commit=False,
            )
            refreshed += 1
    store.conn.commit()
    return refreshed


def _app_version_allows(current: str, minimum: str) -> bool:
    current_version = parse_version(current)
    minimum_version = parse_version(minimum)
    if current_version is None or minimum_version is None:
        return False
    return current_version >= minimum_version


def _seed_db_candidate(seed_directory: Path) -> tuple[Path, str]:
    seed_db = seed_directory / SEED_DB_NAME
    if seed_db.is_file():
        return seed_db, SEED_DB_NAME
    return seed_directory / OFFICIAL_DATA_DB_NAME, OFFICIAL_DATA_DB_NAME


def _expected_seed_sha(manifest: dict[str, Any], seed_db_key: str) -> str:
    if seed_db_key == SEED_DB_NAME:
        return str(manifest.get("sha256") or "").strip().lower()
    files = manifest.get("files")
    if not isinstance(files, dict):
        return ""
    entry = files.get(seed_db_key)
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("sha256") or "").strip().lower()


def _backup_current_db(current_db: Path, backups_dir: Path, version: int) -> Path | None:
    if not current_db.is_file():
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup = backups_dir / f"stock_translator.{version}.sqlite3"
    shutil.copy2(current_db, backup)
    _prune_backups(backups_dir, keep=3)
    return backup


def _prune_backups(backups_dir: Path, *, keep: int) -> None:
    backups = sorted(
        backups_dir.glob("stock_translator.*.sqlite3"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def _int_or_zero(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
