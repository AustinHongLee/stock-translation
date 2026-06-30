# CODEX_HANDOFF_12 — 法人(T86)改用「市場層級」新鮮度判斷

> 由 Claude 整理。修「冷門股法人永遠顯示『缺 N 日』、連按『補這檔』也清不掉」的問題。
> ⚠️ api.py(read 端)與 app.js(UI)要**一起改**才一致；需真機 + 真 DB 驗。不 push。

---

## 0. 根因
`app/web/api.py build_local_data_payload`（約 215–222 行）與 `build_sync_freshness_payload`（約 320 行）
把**法人**的缺口用 `target_date = 股價目標日(昨天交易日)` 來算：
```python
institutional_gap = plan_data_gap(node=DATA_NODE_INSTITUTIONAL, coverage=..., target_date=target_date, ...)
```
但 T86 是「逐日、逐檔」：冷門股很多交易日根本沒有法人進出，那幾天的 T86 就沒有它 → 它的法人最後日永遠 < 股價目標日 → 永遠「法人缺 N 日」。
使用者按「補這檔」→ `sync_institutional` 抓那幾天 T86 → **那幾天本就沒有這檔 → 0 筆 → 仍缺**。資料根本不存在，無法補。

**正解：法人完整度是「市場層級」屬性**——只要全市場 T86 抓到最新交易日，就代表每一檔都已是「能拿到的最新」；冷門股最後日較舊只是「近期沒法人進出」，不是缺料。

> 已先修好(Claude，未 commit)：bulk T86「空日誤標 done → 永久跳過」毒化 bug（`bulk_runner.py`：最近 N 天強制重抓 + 只有有資料才標 done）。本檔處理 read/UI 端。

---

## 1. 後端：改成市場層級（api.py）

### 1.1 helper（放 `app/analyze/data_gap.py`）
```python
def market_node_freshness(latest_date, target_date, *, grace_business_days: int = 1) -> dict:
    """市場層級新鮮度：latest=市場該節點最新日, target=期望最新交易日。"""
    latest = _as_date(latest_date)
    target = _as_date(target_date)
    if target is None:
        return {"status": "source_pending", "gap_business_days": 0, "latest_date": _date_json(latest)}
    if latest is None:
        return {"status": "missing", "gap_business_days": 0, "latest_date": None}
    if latest >= target:
        return {"status": "current", "gap_business_days": 0, "latest_date": _date_json(latest)}
    gap = count_business_days(latest + timedelta(days=1), target)
    status = "current" if gap <= grace_business_days else "gap"
    return {"status": status, "gap_business_days": gap, "latest_date": _date_json(latest)}
```

### 1.2 `build_local_data_payload`
- 進迴圈前算一次市場法人最新日：
  ```python
  inst_dates = store.get_institutional_dates_any()           # 既有方法，回 ISO 字串集合
  market_inst_latest = max((date.fromisoformat(d) for d in inst_dates), default=None)
  expected_close = previous_completed_business_day(today)    # 來自 market_calendar
  market_inst = market_node_freshness(market_inst_latest, expected_close)
  ```
- 每檔 item 的 `institutional_gap` **改用市場層級結果**（所有列相同）；保留每檔自己的 `institutional_last_date`（資訊用）與 `has_institutional`：
  ```python
  "institutional_gap": market_inst,                 # 市場層級（全部一致）
  "institutional_last_date": institutional_coverage.get("latest_date"),
  "has_institutional": sid in inst_ids,
  ```
- 也在 payload 頂層放一份市場法人狀態，給前端做「頁面層提示」：`payload["market_institutional"] = market_inst`。
- **日線維持原本逐檔判斷**（日線確實是逐檔、可逐檔補）。

### 1.3 `build_sync_freshness_payload`（個股頁同理）
法人那段也改用市場層級（market_inst_latest vs expected_close）；別再逐檔跟股價目標日比。

---

## 2. 前端：補這檔=日線專用；法人=市場層級（app.js）

- `localRowNeedsFix(item)` 改成**只看日線**：`return priceNeedsFix(item);`（移除 `instQuickFixable`／`instBigGap` 進入逐列按鈕的判斷）。
- `localFixHint(item)`：只保留日線相關提示；**移除法人逐列提示**。
- 法人狀態改成**頁面層一條**（類似快照 banner）：讀 `payload.market_institutional`，若 `status==="gap"` →
  顯示「法人資料待更新 N 日 · 請按上方『開始下載』補(全市場一次抓)」；`missing` → 「法人尚未下載 · 請按開始下載」。可關。
- 每列「法人」欄改成**純資訊**：顯示該檔 `institutional_last_date`（或 ✓/—），**不再有「法人缺 N 日 + 補這檔」**。
- 結果：全市場 T86 抓到最新 → 每檔法人都顯示「已最新」（含冷門股）；沒抓到 → 一條頁面提示導去開始下載。**不再有逐檔永遠清不掉的法人缺。**

---

## 3. 測試
- `tests/test_data_gap.py`：加 `market_node_freshness`（current/gap/missing/grace 邊界）。
- web 測試：local-data payload 的 `institutional_gap` 全列一致 = `market_institutional`；市場法人最新≥expected → 全部 current（即使某檔自己的法人最後日較舊）。
- 既有 `test_bulk_runner.py` 不動（bulk T86 修補已含其中）。

## 4. Do-NOT
- ❌ 不要再用「股價目標日」逐檔判法人缺。
- ❌ 不要提供逐檔「補法人」(冷門股那幾天本就無資料，補不到)；法人一律走全市場下載。
- ❌ 日線邏輯不要動（日線可逐檔補，維持現狀）。

## 5. 驗收
```
[ ] python -m pytest -q 全綠
[ ] python -m compileall app ; node --check app/ui/static/app.js
[ ] 真機:全市場下載後，本地資料每檔法人=「已最新」(含冷門股)；無逐檔法人缺/補這檔
    若市場 T86 落後 → 頁面一條「法人待更新→開始下載」，下載後消失
```
commit 建議：`Judge institutional (T86) freshness at market level; daily-only per-row fix`，先不要 push。

*bulk T86 毒化修補已由 Claude 套用(未 commit)，請一併 commit。*
