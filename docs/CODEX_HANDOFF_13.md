# CODEX_HANDOFF_13 — 官方資料包(seed)自動合併

> 由 Claude 整理，依 `docs/AUDIT_2026-07-01.md` §3。目標：release 附一份官方 seed，安裝/更新後啟動時
> **把 seed 裡「本地缺的」市場資料補進 LOCALAPPDATA，永不覆蓋、不刪、不碰使用者私有表**。
> 純標準庫；非破壞合併重用 `app/store/legacy_import.py` 的引擎。分階段、每階段可單獨驗收。**不 push。**

---

## 0. 鐵則（違反者測試擋）
- **只新增、不覆蓋、不刪**：一律 `INSERT OR IGNORE`（以 PK 為準）。
- **只碰市場資料表**；`watchlist / portfolio_transactions / chart_annotations / indicator_prefs / app_cache / bulk_progress` **絕不碰**，seed 本身也不含這些表。
- **背景執行、不卡啟動**；失敗安靜、不嚇使用者（合併非破壞，失敗無害）。
- seed 放 **`_internal/seed/`**（不是 exe 旁 `data/`；否則更新器 `robocopy /XD data` 會跳過它）。
- 每個 seed 版本**只合併一次**（version gate）。

---

## 1. Phase 1 — 產生並打包 seed（先只出貨，不合併）

### 1.1 `tools/build_seed.py`（新增）
輸入 dev DB `data/stock_translator.sqlite3`，產出 `dist/seed/seed.sqlite3` + `dist/seed/manifest.json`：
1. 複製 DB → 暫存。
2. **瘦身**：`DELETE FROM daily_prices WHERE date < <今天-370天>`（只留約 1 年廣度底；深歷史交給補這檔）。institutional_trades 同法（留近 1 年）。
3. **清空使用者表**：`DELETE FROM watchlist; DELETE FROM portfolio_transactions; DELETE FROM chart_annotations; DELETE FROM indicator_prefs; DELETE FROM app_cache; DELETE FROM bulk_progress;`（seed 不帶這些）。
4. `VACUUM;`。
5. 算 `sha256(seed.sqlite3)`，寫 `manifest.json`：
```json
{
  "data_snapshot_version": 20260701,          // 用產生日期(YYYYMMDD)，單調遞增
  "generated_at": "2026-07-01T00:00:00Z",
  "app_min_version": "2.0.2",
  "sha256": "<seed.sqlite3 sha256>",
  "tables": { "daily_prices": {"rows": N, "date_min": "...", "date_max": "...", "stocks": M}, "...": {} }
}
```

### 1.2 打包
- `stock_translator.spec` 的 `datas` 加：`(str(ROOT/"dist"/"seed"/"seed.sqlite3"), "seed")`、`(str(ROOT/"dist"/"seed"/"manifest.json"), "seed")` → 進 `_internal/seed/`。
- `build_release.bat`：PyInstaller 前先 `python tools\build_seed.py`。
- **順帶去重（AUDIT L5）**：目前 `build_release.bat:21-24` 又把整個 DB 複製到 exe 旁 `data/`，和 `_internal/data` 重複打包。Phase 1 可先不動（降風險）；Phase 2 完成、first-run 也改走 seed 後再拿掉，避免 zip 帶三份 DB。

### 1.3 runtime 存取
- `runtime_paths.py` 加 `def seed_dir() -> Path: return resource_root() / "seed"`。

**Phase 1 驗收**：build 後 `_internal/seed/` 有 seed.sqlite3+manifest；manifest 的 rows/date_max 與 seed 內容一致；sha 正確。此階段程式不讀 seed（只出貨）。

---

## 2. Phase 2 — 合併引擎 + 啟動時套用

### 2.1 泛化合併（`app/store/legacy_import.py`）
把現有 `import_legacy_data` 底層抽成可指定表的通用函式（**保持 `import_legacy_data` 行為不變**）：
```python
def merge_sqlite(source_db, target_db, tables) -> dict:
    """ATTACH source → 對 tables 逐表 INSERT OR IGNORE(共同欄位) → DETACH。非破壞。"""
    # = 現有 import_legacy_data 的 ATTACH/共同欄位/OR IGNORE 迴圈，tables 改參數化
def import_legacy_data(legacy_db, current_db):        # 保持原樣
    return merge_sqlite(legacy_db, current_db, IMPORTABLE_TABLES)
```

### 2.2 `app/store/seed_merge.py`（新增）
```python
SEED_MERGE_TABLES = (
    "stock_profiles", "daily_prices", "dividend_records", "market_valuations",
    "monthly_revenues", "financial_statements", "institutional_trades", "data_coverage",
)  # 刻意不含 watchlist/portfolio/chart_annotations/indicator_prefs/app_cache/bulk_progress

def read_seed_manifest(seed_dir) -> dict | None       # 讀 manifest.json，壞/缺回 None
def applied_seed_version(store) -> int                 # 讀 app_cache 的 "seed_applied_version"，無回 0
def set_applied_seed_version(store, v) -> None
def maybe_merge_seed(store, *, seed_dir, current_db, app_version, backups_dir) -> dict:
    # 1) manifest = read_seed_manifest(seed_dir); 沒有就 return {"applied": False}
    # 2) app_min_version 比 app_version 新 → 跳過(seed 比 app 新)
    # 3) manifest.data_snapshot_version <= applied_seed_version(store) → 跳過(已套用)
    # 4) 驗 seed.sqlite3 的 sha256 == manifest.sha256；不符 → 跳過
    # 5) 備份 current_db → backups_dir/stock_translator.<version>.sqlite3；只留最近 3 份
    # 6) summary = merge_sqlite(seed.sqlite3, current_db, SEED_MERGE_TABLES)
    # 7) set_applied_seed_version(store, version); store.delete_json_cache("local_data_v2")
    # 8) return {"applied": True, "version": version, **summary}
    # 全程 try/except；任何失敗 return {"applied": False, "error": ...}，絕不 raise
```

### 2.3 接到啟動（`app/web/server.py` main）
- 在 `ensure_seeded_data_file(...)` 之後、且**背景執行緒**裡呼叫：
```python
if getattr(sys, "frozen", False):
    threading.Thread(target=lambda: maybe_merge_seed(
        SQLiteStore(args.db), seed_dir=seed_dir(), current_db=args.db,
        app_version=APP_VERSION, backups_dir=data_dir()/"backups"), daemon=True).start()
```
- **僅 frozen**（dev 的 resource_root 沒有 seed，且不想在開發時亂動）。
- 不可 block 伺服器啟動。

### 2.4 順序與共存
- 啟動：`migrate_legacy_data`（使用者自己的舊資料優先）→ `ensure_seeded_data_file`（首載種子）→ 背景 `maybe_merge_seed`（補官方缺的）。三者都 OR IGNORE，無衝突。
- 與全市場下載/補這檔互補：seed=歷史底、下載=最新日、補這檔=單檔深歷史。
- 與自動更新天生搭配：seed 在 `_internal` → 換版即換新 seed → 下次啟動自動補新。

**Phase 2 驗收（`tests/test_seed_merge.py`）**
- merge 只補本地缺的列、**不覆蓋**既有（改值後合併，值不變）。
- **絕不動** watchlist/portfolio/annotations/prefs（先塞使用者列，合併後不變/不新增）。
- version gate：同版本第二次呼叫 → `applied: False`（不重做）；版本前進 → 會做。
- seed 缺/壞、sha 不符、app_min_version 太新 → `applied: False` 且不崩。
- 合併前有備份檔；備份只留最近 3 份。
- `merge_sqlite` 對欄位漂移容忍（沿用 legacy_import 既有行為）。

---

## 3. Phase 3 — UI / 透明度（小）
- `/api/app-info` 加 `data_snapshot_version`(本地已套用) 與 seed manifest 版本。
- 合併成功 → 一行淡色（非阻斷）：「已補上官方資料包的 N 筆新資料」；失敗 → 不顯示或極淡「官方資料包這次沒套用，不影響你的資料」。
- （可選）設定頁一顆「重新套用官方資料包」＝清 applied 版本後重跑。

## 4. Phase 4（可選、先不做）
差量 seed（只帶上次以來的新資料）縮小 zip。複雜、非必要。

---

## 5. Do-NOT
- ❌ market 表用 `OR REPLACE`（會覆蓋使用者本地資料）。一律 `OR IGNORE`。
- ❌ 合併／打包 watchlist、portfolio、annotations、設定。
- ❌ seed 放 exe 旁 `data/`（更新器會 `/XD data` 跳過）。放 `_internal/seed`。
- ❌ 出 5 年全深度 seed（zip 爆大）。1 年廣度底即可。
- ❌ 同步卡啟動 / 每次都真的合併（要背景 + version gate）。
- ❌ 失敗時彈錯嚇使用者（背景安靜、非破壞）。

---

## 6. 施工順序
```
Phase 1  tools/build_seed.py + spec/build_release 打包 seed + manifest（只出貨）
Phase 2  merge_sqlite 泛化 + seed_merge.py + 啟動背景套用 + test_seed_merge.py
Phase 3  app-info 版本 + 淡色提示（可選重新套用）
Phase 4  差量 seed（可選）
```
每階段：`python -m pytest -q` 全綠、`compileall`。分階段 commit（每次記得 bump 版本再發佈，見記憶 `release-bump-version-each-change`）。**先不要 push。**

---

## 7. Codex 實作狀態
已實作 Phase 1、Phase 2 與 Phase 3 的 app-info 欄位：
- `tools/build_seed.py`
- `runtime_paths.seed_dir()`
- `legacy_import.merge_sqlite(...)`
- `app/store/seed_merge.py`
- frozen 啟動背景套用 seed
- `tests/test_seed_merge.py`

Phase 3 的前端淡色提示與「重新套用官方資料包」按鈕尚未做；Phase 4 差量 seed 先不做。
