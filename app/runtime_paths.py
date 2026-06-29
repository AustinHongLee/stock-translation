from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[1]


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return resource_root()


def external_data_root() -> Path:
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "StockTranslator"
    return resource_root()


def static_dir() -> Path:
    return resource_root() / "app" / "ui" / "static"


def data_dir() -> Path:
    return external_data_root() / "data"


def bundled_data_dir() -> Path:
    return resource_root() / "data"


def data_path(filename: str, *, writable: bool = False) -> Path:
    external = data_dir() / filename
    if writable or external.is_file():
        return external
    return bundled_data_dir() / filename


def ensure_seeded_data_file(filename: str) -> Path:
    target = data_path(filename, writable=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        source = bundled_data_dir() / filename
        if source.is_file():
            shutil.copy2(source, target)
    return target


def migrate_legacy_data(filename: str = "stock_translator.sqlite3") -> bool:
    """Copy exe-adjacent data into the external data directory once.

    Older frozen builds kept writable data next to the executable. New builds keep
    it under LOCALAPPDATA so program updates can replace only application files.
    """
    if not getattr(sys, "frozen", False):
        return False

    target_dir = data_dir()
    target_db = target_dir / filename
    if target_db.exists():
        return False

    legacy_dir = external_root() / "data"
    legacy_db = legacy_dir / filename
    if not legacy_db.is_file():
        return False

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy_dir, target_dir, dirs_exist_ok=True)
        return target_db.is_file()
    except Exception as exc:  # noqa: BLE001 - migration must never block startup
        LOGGER.warning("Failed to migrate legacy data from %s to %s: %s", legacy_dir, target_dir, exc)
        return False
