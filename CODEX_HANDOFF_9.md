# CODEX_HANDOFF_9 — 本地資料「資料狀態」一鍵修正 + 白話引導（已由 Claude 改完）

> 與 HANDOFF_8 同模式：**程式碼 Claude 已改好**。Codex 只需 ①真機跑 `node --check` / 開頁目視 ②commit。push 由使用者決定。
> 設計已與使用者確認：**智慧分流 + 按鈕加白話提示**。

---

## 0. 需求
本地資料表格「資料狀態」出現橘字時，旁邊要有**白話說明 + 一鍵修正**。
關鍵設計點（使用者已選「智慧分流」）：
- **快照待更新 = 全市場共用**（一個檔）→ 放**頁面頂端一顆** banner + 「更新雷達快照」鈕；**不再逐列顯示**。
- **日線缺 / 需重建（或法人缺）= 逐檔** → 在**該列**放「補這檔」鈕（單檔同步）+ 一句白話提示。

---

## 1. 已套用的修改

### 1.1 `app/ui/static/app.js`
- `handleScreenerAction()`：新增兩個委派分支 `[data-refresh-snapshot]`、`[data-local-fix-stock]`（在 `#dataSheet` 既有的委派上）。
- `renderLocalDataTable()`：開頭呼叫 `renderSnapshotBanner(payload)`；每列動作格在「看個股」前，視需要加「補這檔」鈕（`localRowNeedsFix(it)` 為真時）。
- `localDataCoverageLabel()`：**移除逐列「快照待更新」**（改到 banner）；缺資料時在狀態下方加白話小字 `localFixHint(it)`。
- 新增函式：
  - `localGapNeedsFix(gap)` / `localRowNeedsFix(item)`：status 為 `gap` 或 `force_refresh_required` 才需修。
  - `localFixHint(item)`：回「差幾天沒補上 · 按『補這檔』一鍵補回」或「資料對不上 · 按『補這檔』重抓這檔」。
  - `renderSnapshotBanner(payload)`：`payload.data_target.snapshot_stale` 為真時，動態在表格上方插入 `#localDataSnapshotBanner`（白話說明＋「更新雷達快照」鈕）；否則隱藏。**不需改 index.html**（DOM 動態建立）。
  - `fixSnapshotFromLocalData(button)`：呼叫既有 `refreshValueScreener()` → `loadLocalData()`（banner 自動消失）。
  - `fixOneStockFromLocalData(stockId, button)`：呼叫既有 `syncTargetsBatch([sid])`（打 `/api/sync/batch`）→ `loadLocalData()`，補完刷新該列；若該檔正開著也刷新個股。

### 1.2 `app/ui/static/app.css`
在 `.ld-snapshot` 規則後新增 `.ld-hint`、`.ld-fix-btn`、`.ld-banner`、`.ld-banner-text`、`.ld-banner-action`（沿用 `--warn`/`--muted`，無紅綠、無 color-mix，相容性安全）。

**沒有後端改動**：複用既有端點 `POST /api/value-screener/refresh`（雷達快照）與 `POST /api/sync/batch`（單檔）。

---

## 2. 效果（以截圖的味全為例）
- 原本該列：日線已最新 / 法人已最新 / **快照待更新**（橘字混在一起）。
- 改後：該列只剩「日線已最新 / 法人已最新」（乾淨）；**快照待更新變成頁面頂端一條 banner**，含白話＋「更新雷達快照」鈕。
- 若某列日線缺 N 日 / 需重建：該列出現「補這檔」鈕 + 白話小字；按一下→單檔補→該列自動更新。

> 註：HANDOFF_8 的後端修好後，全市場下載完會自動刷新快照 → 多數情況 banner 不會出現；它是補救/引導用的安全網。

---

## 3. 驗收（請在真機）
```
[ ] node --check app/ui/static/app.js          # Claude 已對所有改動函式做隔離 node --check 通過（本沙箱會截斷大檔，無法整檔檢查）
[ ] 開「本地資料」頁目視：
    [ ] 快照舊 → 頂端出現 banner，按「更新雷達快照」→ 轉圈→完成→banner 消失
    [ ] 某列日線缺/需重建 → 出現「補這檔」→ 按→補完該列變「已最新」
    [ ] 日線/法人皆最新的列：無「補這檔」、無多餘橘字
[ ] python -m pytest -q（前端改動不影響，但 test_ui_theme 之類若斷字串需同步——本次無刪既有 DOM id）
```
Claude 在沙箱已驗證：抽出所有新增/修改函式 → `node --check` = **JS SYNTAX OK**。

---

## 4. commit 建議
```
Add one-click fixes + plain-language hints to local-data status
(page-level snapshot banner; per-row 補這檔; smart routing)
```
**先不要 push（由使用者決定）。**

*本檔由 Claude 整理；§1 變更已實際套用於工作樹（未 commit、未 push）。*
