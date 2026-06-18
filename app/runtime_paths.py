from __future__ import annotations

import shutil
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[1]


def external_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return resource_root()


def static_dir() -> Path:
    return resource_root() / "app" / "ui" / "static"


def data_dir() -> Path:
    return external_root() / "data"


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
