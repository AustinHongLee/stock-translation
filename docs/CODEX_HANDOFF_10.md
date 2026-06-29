# CODEX_HANDOFF_10 — 自動更新（檢查＋下載＋一鍵換版）＋ 資料分離

> 給 Codex 的可執行規格。由 Claude 整理。**本檔目前是規格，程式碼尚未實作**（與 8/9 不同）。
> 規則：不 push（由使用者決定）；純標準庫（urllib/zipfile，不加依賴）；分波、每波可單獨驗收。
> 來源已定：**GitHub Releases**。先確認 repo owner/name 填入 §2 的 API URL。

---

## 0. 目標與關鍵設計
- 啟動時（背景）跟 GitHub Releases 比對版本；有新版 → UI 顯示「有新版 vX · 下載並更新 / 直接下載 / 查看說明」。
- 可下載新版並**一鍵換版**（換掉 exe + `_internal`），完成後重開。
- **關鍵：先做「資料分離」**——把 `data` 搬到固定使用者資料夾。更新時**只換程式、不碰資料**，所以「替換資料」變成「資料原地不動、自動接上」。沒有這步就不准做自我替換（會洗掉使用者下載的資料）。

---

## 1. Wave U1 — 資料分離 + 一次性遷移（先做，可單獨上線）

### 1.1 `app/runtime_paths.py`
- 新增「外部**資料**根目錄」（與「外部程式根目錄」分開）：
  ```python
  def external_data_root() -> Path:
      if getattr(sys, "frozen", False):
          base = os.environ.get("LOCALAPPDATA") or str(Path.home())
          return Path(base) / "StockTranslator"   # ASCII 資料夾名，避免路徑編碼問題
      return resource_root()  # 開發模式不變（repo 根）
  ```
- `data_dir()` 改成 `external_data_root() / "data"`（原本是 `external_root()/data` = exe 同層）。
- `bundled_data_dir()` / `ensure_seeded_data_file()` 維持（新位置沒檔才用 bundled seed）。

### 1.2 一次性遷移 `migrate_legacy_data()`（啟動時、開 DB 前呼叫一次）
- 若**新** data_dir 沒有 `stock_translator.sqlite3`，但**舊**位置 `Path(sys.executable).parent/"data"/stock_translator.sqlite3` 存在：
  - 複製整個舊 `data` 內容到新 data_dir（**含** `-wal`、`-shm`、`value_screener.json`、其它檔）。複製成功才算遷移完成；**不刪舊檔**（保留當備份）。
- 在 `server.py` 啟動流程（`ensure_seeded_data_file` 之前）呼叫。
- 失敗安靜不崩（記 log），退回 bundled seed 流程。

### 1.3 驗收 `tests/test_runtime_paths.py`
- monkeypatch `sys.frozen=True` + `LOCALAPPDATA` + `sys.executable` →
  - `data_dir()` 指到 `LOCALAPPDATA/StockTranslator/data`。
  - 遷移：舊位置有 DB、新位置空 → 呼叫後新位置出現 DB（含 sidecar）。
  - 新位置已有 DB → 遷移**不覆蓋**。
  - 開發模式（非 frozen）路徑不變。

> U1 上線後，現有測試者第一次開新版就會自動把 data 搬到固定位置，**之後換版本永遠免搬**。

---

## 2. Wave U2 — 版本比對 + 更新通知（檢查 + 連結）

### 2.1 版本常數
- `app/version.py`：`APP_VERSION = "2.0.0"`（語意化版本；打包時顯示在 UI 角落）。

### 2.2 來源（GitHub Releases）
- `https://api.github.com/repos/<OWNER>/<REPO>/releases/latest` → 取 `tag_name`（如 `v2.1.0`）與 `assets[].browser_download_url`（onedir zip）、`body`（更新說明）。
- 純 `urllib.request`，逾時 ~5s、`User-Agent` 標頭；失敗**安靜**（不可拖垮啟動）。

### 2.3 比對 `app/update/checker.py`（純函式、可測）
- `parse_version("v2.1.0") -> (2,1,0)`；`is_newer(latest, current) -> bool`（語意化，壞格式回 False、不丟例外）。
- `check_for_update(current, fetch_json) -> {"available","latest","url","notes"}`（fetch 注入，方便測）。

### 2.4 端點 + UI
- `GET /api/update/check` → 回 §2.3 結構，`app_cache` 快取數分鐘。
- UI：啟動後背景打一次；有新版 → 頂部一條（或設定頁）：`有新版 vX` + 「下載並更新」「直接下載」「查看說明」+「知道了」可關。
- **隱私**：產品標榜「本地優先·不上傳」→ 加設定開關「自動檢查更新」（預設開、可關），說明寫清楚「只連 GitHub 取版本號，不上傳任何資料」。

### 2.5 驗收 `tests/test_update_checker.py`
- 新版/同版/舊版/壞 tag/缺 asset → 行為正確；網路失敗 → `available=False` 不崩。

---

## 3. Wave U3 — 下載 + 一鍵換版（Windows 自我替換）

### 3.1 下載
- `POST /api/update/download` → 下載 release zip 到 `%TEMP%\StockTranslator_update\`，驗證大小（release 若附 sha256 就比對），解壓到暫存資料夾。
- 失敗回明確錯誤；不動現有安裝。

### 3.2 一鍵換版（關鍵：執行中的 exe/_internal 不能自我覆蓋）
- 寫一支 `updater.bat`（或小型 `updater.exe`）到 `%TEMP%`，主程式啟動它後**自行 exit**。updater：
  1. 等主程式 PID 結束（`tasklist` 輪詢 / `timeout`）。
  2. **先備份**：把安裝資料夾的 `exe`、`_internal` 改名為 `.bak`。
  3. `robocopy` 把新版的 `exe`+`_internal` 覆蓋進安裝資料夾（**只動程式檔**）。
  4. 成功 → 刪 `.bak`、重新啟動主程式；失敗 → 還原 `.bak`、重啟舊版、留錯誤檔。
- **絕不刪/覆蓋 data**（data 已在 LOCALAPPDATA，根本不在安裝資料夾）。

### 3.3 備援（AV 擋自我替換時）
- UI 永遠同時提供「**直接下載**」連結：使用者自己解壓覆蓋程式檔即可；因 data 已分離，**資料自動保留**。

---

## 4. Wave U4 — 打包 / 發佈
- PyInstaller spec / `build_release.bat` 注入 `APP_VERSION`；UI 角落顯示版本。
- 發佈：打 git tag → 上傳 onedir zip 到 GitHub Release（asset 命名穩定，如 `StockTranslator-vX.Y.Z.zip`，附 `sha256`）。
- `README_給測試者.txt`：首次安裝放任意資料夾；更新＝程式內「下載並更新」或「下載新版覆蓋程式檔（data 自動保留）」。

---

## 5. 誠實的限制（要寫進 UI/README）
- **未簽章**：下載的 exe 與自我替換的 .bat，Windows SmartScreen/Defender 可能警告或攔截 → 因此一定要保留「直接下載」備援；長期對外建議辦**程式碼簽章憑證**。
- 公司/受控環境可能鎖寫入 → onedir 放使用者目錄通常 OK。

---

## 6. Do-NOT
- ❌ 沒做 U1（資料分離）前，不准做自我替換（會洗資料）。
- ❌ 自我替換時不准碰 `data`。
- ❌ 更新檢查不准放進會拖垮啟動的路徑（背景、短逾時、失敗安靜）。
- ❌ 不加重依賴（用 `urllib` + 內建 `zipfile`）。

---

## 7. 施工順序與驗收
```
U1 資料分離+遷移+test_runtime_paths      ← 先；可單獨上線（現有測試者資料以後免搬）
U2 version.py + /api/update/check + UI通知 + test_update_checker
U3 下載 + updater.bat 一鍵換版 + 回滾 + 直接下載備援
U4 打包注入版本 + GitHub Release 流程 + README
```
最終：`python -m pytest -q` 全綠；真機驗證：舊 data 自動遷移且資料還在 → 更新通知正確 → 下載+換版後版本變、data 不變 → AV 警告情境有備援連結。
完成後分波 commit，**先不要 push**。

*本檔由 Claude 整理；尚未變更程式碼（規格階段）。建議先做 U1。*
