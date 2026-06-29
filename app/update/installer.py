from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.update.checker import USER_AGENT

UPDATE_WORK_DIR = "StockTranslator_update"
APP_EXE_NAME = "股票翻譯機.exe"


@dataclass(frozen=True)
class PreparedUpdate:
    latest: str
    zip_path: Path
    payload_dir: Path
    updater_path: Path
    manual_url: str
    install_dir: Path


def prepare_update(
    update_info: dict[str, Any],
    *,
    work_root: Path | None = None,
    install_dir: Path | None = None,
    executable: Path | None = None,
    pid: int | None = None,
) -> PreparedUpdate:
    url = str(update_info.get("url") or update_info.get("manual_url") or "").strip()
    if not url:
        raise ValueError("Release 沒有可下載的 zip。")

    latest = str(update_info.get("latest") or "").strip() or "unknown"
    root = work_root or (Path(tempfile.gettempdir()) / UPDATE_WORK_DIR)
    download_dir = root / latest
    extract_dir = download_dir / "extracted"
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    zip_path = download_dir / _safe_zip_name(update_info, latest)
    download_file(url, zip_path, expected_size=int(update_info.get("size") or 0))
    expected_sha256 = str(update_info.get("sha256") or "").strip().lower()
    if not expected_sha256 and update_info.get("sha256_url"):
        expected_sha256 = fetch_remote_sha256(
            str(update_info.get("sha256_url") or ""),
            asset_name=str(update_info.get("asset_name") or zip_path.name),
        )
    if expected_sha256:
        actual_sha256 = file_sha256(zip_path)
        if actual_sha256 != expected_sha256:
            raise ValueError("下載檔案的 SHA-256 不一致，已停止更新。")

    safe_extract_zip(zip_path, extract_dir)
    payload_dir = find_payload_dir(extract_dir)
    exe_path = executable or Path(sys.executable).resolve()
    target_install_dir = install_dir or exe_path.parent
    updater_path = write_updater_bat(
        payload_dir=payload_dir,
        install_dir=target_install_dir,
        executable=exe_path,
        pid=pid or os.getpid(),
        output_dir=download_dir,
    )
    return PreparedUpdate(
        latest=latest,
        zip_path=zip_path,
        payload_dir=payload_dir,
        updater_path=updater_path,
        manual_url=url,
        install_dir=target_install_dir,
    )


def start_prepared_update(prepared: PreparedUpdate) -> None:
    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", str(prepared.updater_path)],
        cwd=str(prepared.updater_path.parent),
        close_fds=True,
    )


def download_file(url: str, target: Path, *, expected_size: int = 0, timeout: float = 60.0) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)
    actual_size = target.stat().st_size
    if actual_size <= 0:
        raise ValueError("下載檔案是空的。")
    if expected_size > 0 and actual_size != expected_size:
        raise ValueError(f"下載大小不一致（收到 {actual_size} bytes，預期 {expected_size} bytes）。")


def fetch_remote_sha256(url: str, *, asset_name: str = "", timeout: float = 10.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    if asset_name:
        match = re.search(rf"([a-fA-F0-9]{{64}})\s+[\*\s]*{re.escape(asset_name)}", text)
        if match:
            return match.group(1).lower()
    match = re.search(r"([a-fA-F0-9]{64})", text)
    return match.group(1).lower() if match else ""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            destination = (target_dir / member.filename).resolve()
            if destination != target_root and target_root not in destination.parents:
                raise ValueError("更新 zip 含有不安全的路徑，已停止解壓。")
        archive.extractall(target_dir)


def find_payload_dir(extract_dir: Path) -> Path:
    candidates = [extract_dir, *[path for path in extract_dir.rglob("*") if path.is_dir()]]
    for candidate in candidates:
        if (candidate / APP_EXE_NAME).is_file() and (candidate / "_internal").is_dir():
            return candidate
    for candidate in candidates:
        exe_files = list(candidate.glob("*.exe"))
        if exe_files and (candidate / "_internal").is_dir():
            return candidate
    raise ValueError("更新 zip 內找不到可替換的程式檔（exe + _internal）。")


def write_updater_bat(
    *,
    payload_dir: Path,
    install_dir: Path,
    executable: Path,
    pid: int,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    updater_path = output_dir / "updater.bat"
    exe_name = executable.name or APP_EXE_NAME
    log_path = output_dir / "updater.log"
    error_path = output_dir / "update-error.txt"
    content = f"""@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "PAYLOAD={payload_dir}"
set "INSTALL={install_dir}"
set "EXE_NAME={exe_name}"
set "PID={pid}"
set "LOG={log_path}"
set "ERROR_FILE={error_path}"
set "BACKUP=%INSTALL%\\.update_backup_%RANDOM%_%RANDOM%"

echo [%date% %time%] StockTranslator updater start > "%LOG%"
echo Waiting for main process %PID%... >> "%LOG%"
:wait_process
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait_process
)

if not exist "%PAYLOAD%\\_internal" goto fail
if not exist "%PAYLOAD%\\%EXE_NAME%" (
  for %%F in ("%PAYLOAD%\\*.exe") do set "EXE_NAME=%%~nxF"
)
if not exist "%PAYLOAD%\\%EXE_NAME%" goto fail

mkdir "%BACKUP%" >> "%LOG%" 2>&1
if errorlevel 1 goto fail

if exist "%INSTALL%\\%EXE_NAME%" move /Y "%INSTALL%\\%EXE_NAME%" "%BACKUP%\\%EXE_NAME%" >> "%LOG%" 2>&1
if exist "%INSTALL%\\_internal" move /Y "%INSTALL%\\_internal" "%BACKUP%\\_internal" >> "%LOG%" 2>&1

robocopy "%PAYLOAD%" "%INSTALL%" /E /XD data /XF updater.bat update-error.txt updater.log >> "%LOG%" 2>&1
set "ROBOCOPY_RC=%ERRORLEVEL%"
if %ROBOCOPY_RC% GEQ 8 goto rollback

if exist "%BACKUP%" rmdir /S /Q "%BACKUP%" >> "%LOG%" 2>&1
echo [%date% %time%] Update succeeded. Data folder was not touched. >> "%LOG%"
start "" "%INSTALL%\\%EXE_NAME%"
exit /b 0

:rollback
echo [%date% %time%] Update failed, rolling back. Robocopy=%ROBOCOPY_RC% >> "%LOG%"
if exist "%INSTALL%\\%EXE_NAME%" del /F /Q "%INSTALL%\\%EXE_NAME%" >> "%LOG%" 2>&1
if exist "%INSTALL%\\_internal" rmdir /S /Q "%INSTALL%\\_internal" >> "%LOG%" 2>&1
if exist "%BACKUP%\\%EXE_NAME%" move /Y "%BACKUP%\\%EXE_NAME%" "%INSTALL%\\%EXE_NAME%" >> "%LOG%" 2>&1
if exist "%BACKUP%\\_internal" move /Y "%BACKUP%\\_internal" "%INSTALL%\\_internal" >> "%LOG%" 2>&1
echo 更新失敗，已嘗試還原舊版。詳見 "%LOG%" > "%ERROR_FILE%"
start "" "%INSTALL%\\%EXE_NAME%"
exit /b 1

:fail
echo [%date% %time%] Update failed before file replacement. >> "%LOG%"
echo 更新失敗，尚未替換程式檔。詳見 "%LOG%" > "%ERROR_FILE%"
if exist "%INSTALL%\\%EXE_NAME%" start "" "%INSTALL%\\%EXE_NAME%"
exit /b 1
"""
    updater_path.write_text(content, encoding="utf-8")
    return updater_path


def _safe_zip_name(update_info: dict[str, Any], latest: str) -> str:
    asset_name = str(update_info.get("asset_name") or "").strip()
    if asset_name.lower().endswith(".zip") and all(char not in asset_name for char in "\\/:*?\"<>|"):
        return asset_name
    safe_latest = "".join(char for char in latest if char.isalnum() or char in ".-_") or "latest"
    return f"StockTranslator-{safe_latest}.zip"
