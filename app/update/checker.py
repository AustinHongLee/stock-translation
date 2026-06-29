from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from typing import Any

RELEASE_API_URL = "https://api.github.com/repos/AustinHongLee/stock-translation/releases/latest"
USER_AGENT = "StockTranslator-Updater/2.0"
DEFAULT_TIMEOUT_SECONDS = 5.0

VersionTuple = tuple[int, int, int]


def parse_version(value: object) -> VersionTuple | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    try:
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]
    except ValueError:
        return None


def is_newer(latest: object, current: object) -> bool:
    latest_version = parse_version(latest)
    current_version = parse_version(current)
    if latest_version is None or current_version is None:
        return False
    return latest_version > current_version


def fetch_latest_release_json(
    url: str = RELEASE_API_URL,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_update(
    current: str,
    fetch_json: Callable[[], dict[str, Any]] = fetch_latest_release_json,
) -> dict[str, Any]:
    try:
        release = fetch_json()
    except Exception:  # noqa: BLE001 - update checks must never block app startup
        return _unavailable(current=current)

    latest = str(release.get("tag_name") or "").strip()
    asset = select_release_asset(release.get("assets") or [])
    notes = str(release.get("body") or "")
    release_page = str(release.get("html_url") or "")
    newer = is_newer(latest, current)
    url = str(asset.get("browser_download_url") or "") if asset else ""
    sha256 = _find_sha256(release, asset_name=str(asset.get("name") or "") if asset else "")
    sha256_url = _find_sha256_asset_url(release, asset_name=str(asset.get("name") or "") if asset else "")
    available = bool(newer and url)

    return {
        "available": available,
        "current": current,
        "latest": latest or current,
        "url": url,
        "manual_url": url,
        "release_page": release_page,
        "notes": notes,
        "asset_name": str(asset.get("name") or "") if asset else "",
        "size": int(asset.get("size") or 0) if asset else 0,
        "sha256": sha256,
        "sha256_url": sha256_url,
        "source": RELEASE_API_URL,
        "message": "" if available else _not_available_message(latest, current, has_asset=bool(asset)),
    }


def select_release_asset(assets: object) -> dict[str, Any] | None:
    if not isinstance(assets, list):
        return None
    zip_assets: list[dict[str, Any]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if name.lower().endswith(".zip") and url:
            zip_assets.append(item)
    if not zip_assets:
        return None

    preferred_words = ("stocktranslator", "stock-translator", "股票翻譯機")
    for item in zip_assets:
        normalized = str(item.get("name") or "").lower()
        if any(word in normalized for word in preferred_words):
            return item
    return zip_assets[0]


def _find_sha256(release: dict[str, Any], *, asset_name: str) -> str:
    body = str(release.get("body") or "")
    if asset_name:
        pattern = rf"([a-fA-F0-9]{{64}})\s+[\*\s]*{re.escape(asset_name)}"
        match = re.search(pattern, body)
        if match:
            return match.group(1).lower()
    match = re.search(r"sha256\s*[:=]\s*([a-fA-F0-9]{64})", body, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return ""


def _find_sha256_asset_url(release: dict[str, Any], *, asset_name: str) -> str:
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return ""
    sha_assets: list[dict[str, Any]] = []
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if name.lower().endswith((".sha256", ".sha256.txt")) and url:
            sha_assets.append(item)
    if not sha_assets:
        return ""
    if asset_name:
        target = asset_name.lower()
        for item in sha_assets:
            name = str(item.get("name") or "").lower()
            if target in name:
                return str(item.get("browser_download_url") or "")
    return str(sha_assets[0].get("browser_download_url") or "")


def _unavailable(*, current: str) -> dict[str, Any]:
    return {
        "available": False,
        "current": current,
        "latest": current,
        "url": "",
        "manual_url": "",
        "release_page": "",
        "notes": "",
        "asset_name": "",
        "size": 0,
        "sha256": "",
        "sha256_url": "",
        "source": RELEASE_API_URL,
        "message": "暫時無法檢查更新。",
    }


def _not_available_message(latest: str, current: str, *, has_asset: bool) -> str:
    if not latest or parse_version(latest) is None:
        return "Release 版本格式無法辨識。"
    if is_newer(latest, current) and not has_asset:
        return "找到新版，但 Release 沒有可下載的 zip。"
    return "目前已是最新版本。"
