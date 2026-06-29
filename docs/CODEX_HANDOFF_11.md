# CODEX_HANDOFF_11 — 首次開啟「智慧匯入舊資料」

> 解決：新版資料改存 LOCALAPPDATA 後，若使用者「先開過程式」(已種空 DB)，之後才把舊版 exe 旁的 data 放回，
> `migrate_legacy_data` 會因「目標已存在」跳過 → 舊資料吃不進去。本功能改用「**偵測 → 詢問 → 非破壞性併入**」。
>
> ⚙️ **核心已由 Claude 寫好並測過**（`app/store/legacy_import.py` + `tests/test_legacy_import.py`，7/7 綠）。
> Codex 只要做 **API 接線 + 前端詢問 UI + 一條 web 測試**，然後 commit。不 push（使用者決定）。

---

## 1. 已完成（請直接用，勿重寫）

`app/store/legacy_import.py`（純標準庫、對 schema 漂移容忍、INSERT OR IGNORE 非破壞性）：
- `count_daily_stocks(db_path) -> int`
- `legacy_import_status(legacy_db, current_db) -> {available, legacy_stock_count, current_stock_count}`
  （available = 舊 DB 存在、與現用 DB 不同檔、且舊 DB 股票數 > 現用）
- `import_legacy_data(legacy_db, current_db) -> {imported:{table:added}, tables, rows}`
  （ATTACH 舊 DB → 白名單表逐一 `INSERT OR IGNORE`(只取兩邊共同欄位)→ commit；排除 app_cache / bulk_progress）
- `copy_legacy_snapshot(legacy_dir, current_dir, filename="value_screener.json") -> bool`

路徑來源（`app/runtime_paths.py`）：
- 現用 DB：`data_dir() / "stock_translator.sqlite3"`（= LOCALAPPDATA）
- 舊 DB：`external_root() / "data" / "stock_translator.sqlite3"`（= exe 同層）
- 舊資料夾：`external_root() / "data"`

---

## 2. 你要做的

### 2.1 後端端點（`app/web/server.py`，比照既有 update 端點風格）
- `GET /api/data/legacy-import`：
  - **僅 frozen 模式**才偵測（`getattr(sys,"frozen",False)`；dev 模式 external_root=repo 根，data/ 有種子會誤判 → 一律回 available:false）。
  - 回 `legacy_import_status(legacy_db, current_db)` 的內容；若 dismiss 標記存在 → `available:false`、加 `"dismissed": true`。
- `POST /api/data/legacy-import`：
  - `summary = import_legacy_data(legacy_db, current_db)`；`copy_legacy_snapshot(legacy_dir, data_dir())`；
  - `store.delete_json_cache(LOCAL_DATA_CACHE_KEY)`；寫 dismiss 標記（匯入後就別再問）；
  - 回 `{"ok": true, **summary}`。
- `POST /api/data/legacy-import/dismiss`：建立 dismiss 標記 → `{"ok": true}`。
- **dismiss 標記**：`data_dir() / ".legacy_import_dismissed"`（空檔即可；放 LOCALAPPDATA → 跨版本持久）。

### 2.2 前端（`app/ui/static/app.js`，啟動時、app-info 之後呼叫一次）
- `GET /api/data/legacy-import` → 若 `available`：跳一個**中性、非阻斷**的詢問（modal 或頂部列）：
  > 「偵測到你電腦裡有舊版下載的股票資料（約 **N** 檔），目前程式的資料還是空的（約 **M** 檔）。要把舊資料**匯入**嗎？」
  > 〔匯入舊資料〕〔不要，謝謝〕
- 〔匯入舊資料〕→ `POST /api/data/legacy-import` → 成功後 `showMessage("已匯入 N 檔…")`、重新 `loadLocalData()`（若有雷達也刷新）、關掉詢問。
- 〔不要，謝謝〕→ `POST /api/data/legacy-import/dismiss` → 關掉、之後不再問。
- 失敗要有友善訊息；整段不可影響正常啟動。

### 2.3 測試
- `tests/test_legacy_import.py` 已存在（Claude 寫，7/7 綠）—**不要動**。
- 新增一條 web 測試：mock `legacy_import_status` 回 available → `GET /api/data/legacy-import` 形狀正確；`POST .../dismiss` 後再 GET → available:false。

---

## 3. 護欄 / Do-NOT
- ❌ 偵測**僅限 frozen**（dev 模式永遠 available:false，避免拿 repo 的 data/ 誤判）。
- ❌ 匯入**非破壞性**：只用 helper 的 `INSERT OR IGNORE`，**不覆蓋**現用資料、**不刪**舊檔。
- ❌ 不自動匯入：一定要使用者按「匯入」才執行。
- ❌ 不要 import app_cache / bulk_progress（helper 已排除）。

## 4. 驗收
```
[ ] python -m pytest -q   （含 test_legacy_import.py 與新 web 測試，全綠）
[ ] python -m compileall app ; node --check app/ui/static/app.js
[ ] frozen 包實測：先開程式(LOCALAPPDATA 空)→ 關 → 把舊 data 放 exe 同層 → 再開
    → 跳「要匯入嗎」→ 按匯入 → 本地資料出現舊股票；按「不要」→ 之後不再問
```
完成後 commit（建議：`Add first-run legacy data import prompt (detect + non-destructive merge)`），先不要 push。

*核心已套用且測試通過；本檔描述其餘 API/UI 接線。*
