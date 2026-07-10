from __future__ import annotations

import re
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.update.checker import USER_AGENT
from app.update.installer import (
    download_file,
    fetch_remote_sha256,
    file_sha256,
    safe_extract_zip,
)

DATA_HUB_RELEASE_API_URL = "https://api.github.com/repos/AustinHongLee/stock-translation/releases/latest"
DATA_HUB_WORK_DIR = "StockTranslator_data_hub"
DATA_HUB_ZIP_RE = re.compile(r"(?:official[-_]?data|data[-_]?hub).*?(20\d{6}).*?\.zip$", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedDataHub:
    version: int
    zip_path: Path
    hub_dir: Path


def fetch_latest_data_hub_release_json(
    url: str = DATA_HUB_RELEASE_API_URL,
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        import json

        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def check_for_data_hub(
    current_snapshot_version: int,
    fetch_json: Callable[[], dict[str, Any]] = fetch_latest_data_hub_release_json,
    *,
    include_current: bool = False,
) -> dict[str, object]:
    try:
        release = fetch_json()
    except Exception as exc:  # noqa: BLE001 - hub is best-effort
        return _unavailable(current_snapshot_version, f"資料樞紐暫時無法檢查：{exc}")

    asset = select_data_hub_asset(release.get("assets") or [])
    if asset is None:
        return _unavailable(current_snapshot_version, "最新 Release 沒有官方資料樞紐 zip。")

    version = parse_data_hub_version(str(asset.get("name") or ""))
    if version <= 0:
        return _unavailable(current_snapshot_version, "官方資料樞紐檔名缺少資料版本。")

    if not include_current and version <= int(current_snapshot_version or 0):
        return {
            "available": False,
            "current_version": int(current_snapshot_version or 0),
            "version": version,
            "message": "本地資料包已是最新或更新。",
        }

    asset_name = str(asset.get("name") or "")
    url = str(asset.get("browser_download_url") or "")
    return {
        "available": True,
        "current_version": int(current_snapshot_version or 0),
        "version": version,
        "asset_name": asset_name,
        "url": url,
        "manual_url": url,
        "size": int(asset.get("size") or 0),
        "sha256": _find_data_hub_sha256(release, asset_name=asset_name),
        "sha256_url": _find_data_hub_sha256_asset_url(release, asset_name=asset_name),
        "release_page": str(release.get("html_url") or ""),
        "message": "找到較新的官方資料樞紐。",
    }


def prepare_data_hub(
    hub_info: dict[str, Any],
    *,
    work_root: Path | None = None,
) -> PreparedDataHub:
    url = str(hub_info.get("url") or hub_info.get("manual_url") or "").strip()
    if not url:
        raise ValueError("資料樞紐沒有可下載的 zip。")

    version = int(hub_info.get("version") or 0)
    if version <= 0:
        raise ValueError("資料樞紐缺少有效版本。")

    root = work_root or (Path(tempfile.gettempdir()) / DATA_HUB_WORK_DIR)
    download_dir = root / str(version)
    extract_dir = download_dir / "extracted"
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    zip_path = download_dir / _safe_hub_zip_name(hub_info, version)
    download_file(url, zip_path, expected_size=int(hub_info.get("size") or 0))
    expected_sha256 = str(hub_info.get("sha256") or "").strip().lower()
    if not expected_sha256 and hub_info.get("sha256_url"):
        expected_sha256 = fetch_remote_sha256(
            str(hub_info.get("sha256_url") or ""),
            asset_name=str(hub_info.get("asset_name") or zip_path.name),
        )
    if expected_sha256 and file_sha256(zip_path) != expected_sha256:
        raise ValueError("資料樞紐 zip 的 SHA-256 不一致，已停止套用。")

    safe_extract_zip(zip_path, extract_dir)
    return PreparedDataHub(version=version, zip_path=zip_path, hub_dir=find_data_hub_dir(extract_dir))


def find_data_hub_dir(extract_dir: Path) -> Path:
    candidates = [extract_dir, *[path for path in extract_dir.rglob("*") if path.is_dir()]]
    for candidate in candidates:
        if (candidate / "manifest.json").is_file() and (
            (candidate / "seed.sqlite3").is_file()
            or (candidate / "data" / "stock_translator.sqlite3").is_file()
        ):
            return candidate
    raise ValueError("資料樞紐 zip 內找不到 manifest.json 與資料庫。")


def select_data_hub_asset(assets: object) -> dict[str, Any] | None:
    if not isinstance(assets, list):
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        version = parse_data_hub_version(name)
        if version > 0 and url:
            candidates.append((version, item))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def parse_data_hub_version(asset_name: str) -> int:
    match = DATA_HUB_ZIP_RE.search(asset_name)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _find_data_hub_sha256(release: dict[str, Any], *, asset_name: str) -> str:
    body = str(release.get("body") or "")
    if asset_name:
        match = re.search(rf"([a-fA-F0-9]{{64}})\s+[\*\s]*{re.escape(asset_name)}", body)
        if match:
            return match.group(1).lower()
    return ""


def _find_data_hub_sha256_asset_url(release: dict[str, Any], *, asset_name: str) -> str:
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return ""
    expected_names = {
        f"{asset_name}.sha256",
        f"{asset_name}.sha256.txt",
        asset_name.replace(".zip", ".zip.sha256"),
        asset_name.replace(".zip", ".sha256"),
    }
    fallback = ""
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if not url or not name.lower().endswith((".sha256", ".sha256.txt")):
            continue
        if name in expected_names:
            return url
        if ("official-data" in name.lower() or "data-hub" in name.lower()) and not fallback:
            fallback = url
    return fallback


def _safe_hub_zip_name(hub_info: dict[str, Any], version: int) -> str:
    asset_name = str(hub_info.get("asset_name") or "").strip()
    if asset_name.lower().endswith(".zip") and all(char not in asset_name for char in "\\/:*?\"<>|"):
        return asset_name
    return f"StockTranslator-official-data-{version}.zip"


def _unavailable(current_snapshot_version: int, message: str) -> dict[str, object]:
    return {
        "available": False,
        "current_version": int(current_snapshot_version or 0),
        "version": 0,
        "message": message,
    }
