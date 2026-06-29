# CODEX_HANDOFF_8 — 全市場下載補正（已由 Claude 改完，Codex 只需驗證 + git）

> ⚠️ 與前幾份不同：**這次程式碼 Claude 已經改好並通過針對性測試**。
> Codex 的工作只有兩件：①在真機跑完整 `pytest` 與 compile（這台沙箱會截斷大檔，Claude 無法在此跑全套）；②commit。
> **不要重寫、不要「順手修」下面標示『非 bug／勿動』的項目。** push 與否由使用者決定。

---

## 0. 這次解的症狀

使用者回報：**全市場下載「完成」後，本地資料分頁仍整片顯示「快照待更新／日線缺 N 日／日線需重建」，只有法人有更新。重按下載也補不回來。**

根因鏈（已驗證）：
1. 日線逐檔抓，遇 TWSE 限流時 `fetch_daily_prices` **吞掉該月、只記 warning、不丟例外** → `sync_one` 收不到例外。
2. 舊 `sync_one` **無條件標 done**（即使只抓到舊月份）。
3. 舊 `skip()` 看到 `bulk_progress=="done"` 就**永久短路跳過** → 過期股票重下載也不再抓。
4. `target_date` 用 `previous_business_day(today)`，在交易日**會回傳今天本身** → 與 local-data 的 expected（昨天交易日）不一致。
5. 「快照待更新」來自 value_screener 快照沒跟著全市場下載一起更新（兩個更新動作各走各的）。

---

## 1. 已套用的修改（檔案：`app/sync/bulk_runner.py`）

全部在 `build_bulk_plan()` 內，**只動這一個檔**（外加測試）。

### 1.1 `target_date` 對齊「今天之前最後一個交易日」
```python
# 舊：target_date = previous_business_day(today)        # 交易日會回傳今天 → 盤中全被判過期
# 新：
target_date = previous_business_day(today - timedelta(days=1))
```
`previous_business_day` = `previous_twse_trading_day`（節假日感知），所以這就是 local-data 用的
`market_calendar.previous_completed_business_day(today)`，兩邊從此一致。

### 1.2 `sync_one()` — 驗收「真的到最新」才 done（P0-2）
抓完後用 **本地實際最後一筆日期** 驗收：`latest>=target` 才標 `done`；否則標 `failed`（帶人類可讀原因）。
因為 `fetch_daily_prices` 半套不丟例外，這是唯一能擋住「半套被當完成」的關卡。
真正的抓取例外仍 `raise`（保留 bulk.py 的連續失敗自動暫停保護）。

### 1.3 `skip()` — 改用新鮮度，不再用 "done" 短路（P0-1）
```python
# 舊：if bulk_progress[sid]=="done": return True   # 永久跳過，過期也不補
# 新：每次都比對本地最後一筆 vs target_date
latest = store.get_daily_prices(sid, limit=1)
if latest and latest[-1].date >= target_date:
    store.mark_bulk_item(..., "done"); return True
return False
```
過期（含曾被標 done 的）一律回 False → 會被重抓。已最新才跳過。

### 1.4 `on_finish()` — 加「全市場最新日 top-up」+「同步刷新雷達快照」（P1-3 + P1-5）
```python
# 1) STOCK_DAY_ALL 一次補齊所有人的最近收盤（逐檔遇限流時的安全網）。
#    放收尾、不放 prelude：放 prelude 會讓首次下載時 skip() 看到「已有最新一根」
#    而略過逐檔歷史回補，導致每檔只剩 1 根。
latest_all = client.fetch_latest_all_prices(); store.upsert_daily_prices(latest_all)
# 2) refresh_value_screener(client)：讓「全市場下載」也更新 value_screener 快照，
#    否則本地資料每列都掛「快照待更新」。把兩個更新動作綁在一起。
```
（兩者都 try/except 包好；retry_failed_only 模式不做。）

---

## 2. 個股同步 / 雷達中心 的稽查結論（依使用者要求）

- **個股同步 `service.sync_stock_history`**：**沒有**永久跳過 bug（不經 bulk_progress）。
  走 `plan_data_gap` + `resolve_post_patch_status`，半套會標 source_pending/suspect，不會誤判完成。
  唯一小不一致：預設 `target_date = previous_business_day(end_date)`（交易日=今天），但 UI 呼叫時會帶
  freshness 的 `reference_latest_date`（=昨天交易日），所以**實務上一致**。**本輪不改**（避免動 test_sync_service）；
  若要更乾淨，可把預設改成 `previous_business_day(end_date - 1day)`，但屬 nice-to-have。
- **雷達 `refresh_value_screener`**：本身**每次都重抓全市場重建**，無 skip bug。
  原本的問題只是它跟全市場下載**各走各的** → 已用 §1.4 綁在一起解決。

---

## 3. ❌ 非 bug／勿動（Claude 一度懷疑、查證後撤回）

> 這幾項看起來像 bug，實際上**已正確**，**請 Codex 不要去改**，以免製造回歸。

- **市場日曆節假日**：`data_gap.previous_business_day = previous_twse_trading_day`、
  `count_business_days = count_twse_trading_days`，**都已是節假日感知**。
  `market_calendar` 透過它們間接也正確（測試 `previous_completed_business_day(6/22)=6/18` 跳過端午就是證據）。
- **`count_business_days` 缺口天數**：同上，已用交易日曆，不會把假日算成缺。

---

## 4. 已知殘留（可接受，列出供知情）

- 真的停牌／新上市／當日無成交的少數股，`latest<target` → 會標 `failed`（誠實，不再假裝 done）；
  下次下載或「重試失敗」會再嘗試，補不到就維持 failed。屬正確行為。
- `on_finish` 的 `refresh_value_screener` 會再抓一次 profiles/最新價/股利（與 prelude 部分重複），
  每次全市場下載尾端多花一點時間。**可選優化**：把 prelude 已抓的資料共用給 screener，省一輪。本輪未做。

---

## 5. Codex 的驗收清單（請在真機跑）

```
[ ] python -m pytest -q                     # 必須全綠（本機沙箱會截斷 api.py/app.js 等大檔，Claude 只能跑子集）
[ ] python -m compileall app
[ ] tests/test_bulk_runner.py 全綠          # Claude 在此已驗證 5/5 passed
```
Claude 在沙箱已驗證：`tests/test_bulk_runner.py` 5/5 通過；其餘可載入的測試 **290 passed**；
失敗的 8 項全部是沙箱 mount **截斷大檔**（app.js 6984<7332、index.html 1189<1212、api.py 1866<1914…）造成，
**沒有一項碰 bulk_runner**，真機應全綠。

### 新增/更新的測試（`tests/test_bulk_runner.py`）
- `test_sync_one_..._marks_done_when_current`：到最新 → done；`coverage_refreshes` 的 target=2026-02-11（CNY 後對齊）。
- `test_sync_one_marks_failed_when_still_behind_target`：抓回來仍落後 → failed、且**不**標 done。
- `test_skip_refetches_stale_stock_even_if_previously_done`：過期（曾 done）→ 不跳過；已最新 → 跳過；無資料 → 不跳過。
- `test_on_finish_tops_up_latest_and_refreshes_radar_snapshot`：呼叫 STOCK_DAY_ALL top-up + `refresh_value_screener` + 清快取。

---

## 6. commit 建議

```
Fix full-market download freshness: re-check staleness on skip, only mark done when caught up,
add STOCK_DAY_ALL top-up, refresh radar snapshot on finish
```
**先不要 push（由使用者決定）。**

*本檔由 Claude 整理；§1 的程式碼變更已實際套用於工作樹（未 commit、未 push）。*
