# CODEX_HANDOFF_4 — 市場心智雷達（Market Mind Radar，Phase 2）

> 給 Codex 的可直接執行指令。延續 `CODEX_HANDOFF_3.md`（結構指紋，已完成 commit `89218b8`）。
> **設計決策已鎖定，照做即可。** 規則底線不變：**描述現在、不預測未來、不給買賣訊號**；違反者單元測試擋下。
> 由 Claude 整理。本文件未 commit/未 push。

---

## 0. 一句話

把「個股結構指紋」升級到**市場層級**：算「現在整個市場像不像一顆同步的腦」，做成「雷達中心」的新分頁。**全部是狀態描述，不是崩盤預告。**

---

## 1. 硬前提與現況（先讀）

- **資料前提**：Phase 2 需要**跨股截面資料**——至少 **30 檔**、且在最近視窗有**足夠共同交易日**。這要先在「本地資料」跑過**全市場下載**（或至少同步數十檔）。資料不足時，雷達**不可報錯**，要顯示「資料不足，請先完成全市場下載」。
- **沿用 Phase 1**：`app/analyze/structure_metrics.py`（純 Python 引擎）、`structure_registry.py`、個股指紋卡已上線。Phase 2 是**新增**，不要動 Phase 1。
- **命名解鎖**：市場層級現在可以用有記憶點的名字「**市場心智雷達**」（Phase 1 鎖定它不准用在個股，Phase 2 開放）。

---

## 2. 已鎖定的決策（不要再問）

1. **MVP 三個市場指標**：`市場波動`（截面離散度）、`羊群程度`（平均成對相關 ρ̄）、`同步度`（相關矩陣最大模態佔比）。
2. **Kuramoto r、雪崩冪律**：本輪**不做**（列實驗/後續）。理由：Kuramoto 要逐檔相位、雪崩冪律擬合不穩，先把三個穩的做對。
3. **純 Python**：不引入 numpy/scipy（與專案一致）。最大特徵值用 **power iteration**，不要引線代庫。
4. **宇宙(universe)有上限**：為控成本，預設取「本地有日線、且成交值最高的前 **150** 檔」當截面宇宙（可設定）。不要對全市場上千檔做 O(M²)。
5. **視窗**：預設 **120** 個交易日（截面相關常用區間；比個股的 250 短，因為要有共同覆蓋）。
6. **降級**：宇宙 <30 檔 或 共同交易日 <60 → 整個雷達回 `available=False` + 白話「資料不足」。
7. **快取**：市場級結果用 `app_cache`，key 含「最後共同交易日 + 宇宙簽章 + 視窗」。
8. **不預測**：高同步/高相關**只描述**「現在大家走得很像」，**嚴禁**寫成「崩盤前兆/即將反轉」。

---

## 3. Wave M1 — 跨股截面載入器 `app/analyze/cross_section.py`

**目的**：把多檔日線對齊成「報酬矩陣」，供市場指標使用。純函數、可單元測試。

### 3.1 介面
```python
@dataclass(frozen=True, slots=True)
class ReturnsMatrix:
    stock_ids: list[str]          # 欄（M 檔）
    dates: list[str]              # 列（W 個共同交易日，升冪）
    returns: list[list[float]]    # W×M 的 log return；對齊後無缺值
    def to_json(self) -> dict: ...

def build_returns_matrix(
    series_by_stock: dict[str, list[tuple[str, float]]],  # stock_id -> [(date, close)]
    *, window: int = 120, min_stocks: int = 30, min_days: int = 60,
) -> ReturnsMatrix | None:
    """取交集交易日、算 log return、丟掉共同覆蓋不足的檔；不足門檻回 None。"""
```

### 3.2 規則
- 先求所有檔的**交易日交集**，取最近 `window` 天。
- 只保留在這些日子**全部有值**的股票（避免補值汙染）。
- 對每檔在這些日子算 log return（W-1 列 × M 欄）。
- 結果檔數 <`min_stocks` 或共同日 <`min_days` → 回 `None`（上層顯示資料不足）。
- **資料來源由上層注入**（從 `SQLiteStore` 撈），載入器本身純函數、好測試。

### 3.3 驗收（`tests/test_cross_section.py`）
- 對齊正確（交集日、無缺值）。
- 檔數/天數不足 → `None`。
- 故意錯位日期 → 仍正確取交集。

---

## 4. Wave M2 — 市場結構指標 `app/analyze/market_structure.py`

> 全部純 Python。輸入 `ReturnsMatrix`。每個指標回 `MetricSnapshot`（可重用 `structure_metrics.MetricSnapshot`）。

### 4.1 市場波動（截面離散度）`cross_sectional_dispersion`
- **定義**：最後一個交易日，各股報酬的標準差（cross-section std）。輸出最新值 + 在視窗內的百分位。
- **白話**：高 = 今天個股之間「各走各的、分化大」；低 = 大家動得差不多。
- **禁止**：不得當「要變盤」。

### 4.2 羊群程度（平均成對相關）`average_pairwise_correlation`
- **定義**：對 W×M 報酬算 M×M 皮爾森相關矩陣，取**非對角平均** ρ̄ ∈[-1,1]。
- **成本**：O(M²·W)（M≤150 可接受，且有快取）。先把每欄標準化（減均值除標準差）再內積即可。
- **白話**：ρ̄ 高 = 市場越來越像「一顆腦」（系統性連動高，分散風險效果差）；低 = 個股各自表現。
- **禁止**：高相關 ≠ 會跌；只描述連動程度。

### 4.3 同步度（最大模態佔比）`market_mode_share`
- **定義**：相關矩陣的**最大特徵值 λ₁**佔比 `λ₁ / M`（也叫 market mode）。用 **power iteration** 求 λ₁（不用線代庫）：隨機起始向量，反覆 `v ← C·v; v ← v/‖v‖`，收斂後 `λ₁ = vᵀC·v`。
- **範圍**：獨立 → λ₁/M ≈ 1/M（小）；全同向 → λ₁/M ≈ 1。
- **白話**：高 = 有一個「共同因子」在帶動幾乎所有股票（同步性高）；低 = 沒有單一主導力量。
- **禁止**：不得當方向或時點訊號。

### 4.4 合成資料黃金測試（`tests/test_market_structure.py`，**合併門檻**）
用已知結構驗證，不需真資料：
- **獨立**：M 檔各自 i.i.d. 高斯 → ρ̄ ≈ 0、λ₁/M 接近 1/M、離散度為某基準。
- **單因子**：每檔 `r = β·F + ε`（共同因子 F）→ ρ̄ 明顯 >0、λ₁/M 明顯偏高。
- **全同步**：所有檔 = 同一序列 + 微噪 → ρ̄ ≈ 1、λ₁/M ≈ 1。
- power iteration 對已知對稱矩陣的 λ₁ 與暴力法（小 M）誤差在容忍內。

---

## 5. Wave M3 — API + 市場心智雷達分頁

### 5.1 組裝 `build_market_radar_payload(store, *, window=120, universe_size=150)`
- 取宇宙（本地有日線、成交值前 N）→ `build_returns_matrix` → 三指標 → 套 registry 文案。
- 不足門檻 → `{"available": False, "reason": "資料不足，請先在『本地資料』完成全市場下載（至少 30 檔、近 60 個交易日）。"}`。

### 5.2 API
- `GET /api/market/radar`（新端點）。
- **快取**：`app_cache`，key=`f"market_radar::{last_common_date}::{universe_hash}::{window}"`。
- 計算可能較重 → 一定要快取；**不要**放進任何既有熱路徑（local-data / 個股頁）。

### 5.3 回傳形狀
```json
{
  "available": true,
  "as_of_date": "2026-06-22",
  "universe_size": 150,
  "window": 120,
  "title": "市場心智雷達",
  "subtitle": "現在整個市場的結構狀態（描述，非預測）",
  "disclaimer": "市場結構描述 · 描述現在 · 不預測未來 · 非投資建議",
  "metrics": [
    {"key":"dispersion","label":"市場波動(分化)","value":1.8,"percentile":62,"grade":"high",
     "summary":"今天個股之間分化偏大。","forbidden":"不得當變盤訊號。"},
    {"key":"herding","label":"羊群程度","value":0.41,"grade":"high",
     "summary":"平均成對相關 0.41：市場連動偏高。","forbidden":"高相關 ≠ 會跌。"},
    {"key":"synchrony","label":"同步度","value":0.33,"grade":"high",
     "summary":"最大模態佔 33%：有單一共同因子在帶動。","forbidden":"不得當方向或時點訊號。"}
  ]
}
```

### 5.4 前端（雷達中心新分頁）
- 在「雷達中心」加新分頁「**市場心智雷達**」，跟「收盤快照排行」並列，**不取代**現有排行。
- 三個量：用儀表/長條 + 白話 summary + hover 的 `forbidden` + 連 glossary。
- **顏色禁紅綠**（中性藍/灰）。頂部常駐免責。
- 資料不足 → 顯示 reason + 一顆「去本地資料下載」的引導鈕。

### 5.5 glossary 補詞
`市場波動(分化)`、`羊群程度`、`同步度`，`how_to_read` 必含「這是描述、不是買賣指令」。

---

## 6. Wave M4（可選）— 報告 + 實驗區

- 雷達快照併入既有匯出（可選）。
- **實驗室(預設關)**：Kuramoto r、雪崩冪律——若做，放實驗分頁、強免責、標「實驗性」。本輪可不做。

---

## 7. 紅線測試（強制）

擴充 `tests/test_structure_guardrails.py` 或新增 `test_market_guardrails.py`：掃 registry 文案 + `build_market_radar_payload` 範例輸出 + 雷達 HTML，不得出現：
```
會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊|前兆
Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price
```
（注意新增「**前兆**」——同步/相關不准寫成崩盤前兆。）每個指標必須有非空 `forbidden`。

---

## 8. 絕對不要做（Do-NOT）

- ❌ 不要把高同步/高相關寫成「崩盤前兆/即將反轉/該減碼」。
- ❌ 不要對全市場上千檔硬算 O(M²)（用 universe 上限 + 快取）。
- ❌ 不要引入 numpy/scipy（power iteration 純 Python）。
- ❌ 不要把市場計算放進 local-data / 個股頁熱路徑。
- ❌ 不要動 Phase 1 的 structure_metrics / registry / 個股卡。
- ❌ 沒有合成資料黃金測試的指標不准合進 main。

---

## 9. 施工順序與最終驗收

```
Wave M1  cross_section.py + test_cross_section.py（對齊/降級）
Wave M2  market_structure.py + test_market_structure.py（合成資料黃金測試全綠）
Wave M3  build_market_radar_payload + /api/market/radar + 雷達中心新分頁 + glossary + 快取
Wave M4  (可選) 報告/實驗室
```
最終：
```
[x] python -m pytest -q 全綠（既有 + 新增）
[x] python -m compileall app ；node --check app/ui/static/app.js
[x] 紅線測試含「前兆」；每指標 forbidden 非空
[x] 資料充足時雷達顯示三量；資料不足時優雅降級 + 引導下載
[x] /api/market/radar 有快取；未污染 local-data / 個股頁
```
完成後 commit（建議訊息：`Add market mind radar (cross-section + market structure)`），**先不要 push**，交回檢視。

完成記錄（Codex 2026-06-24）：
- 已新增 `cross_section.py` 與 `market_structure.py`，含對齊、降級、平均相關、power iteration 最大模態。
- 已新增 `/api/market/radar`、`app_cache` 快取、雷達中心「市場心智雷達」區塊、三個 glossary 詞條。
- 已補 `test_cross_section.py`、`test_market_structure.py`、`test_market_guardrails.py`，並擴充 web API、UI、glossary 測試。
- 驗證：`python -m pytest -q` = 301 passed / 4 subtests passed；`python -m compileall app` 通過；`node --check app/ui/static/app.js` 通過；`git diff --check` 通過；HTTP smoke `/api/market/radar` 在空 DB 正常回 unavailable。

---

## 10. 給 Codex 的數值碼提示

power iteration 要設最大迭代數與收斂門檻、處理零向量/退化矩陣；相關矩陣先標準化各欄；所有指標**先寫合成資料黃金測試再寫實作**。純 Python、明確邊界、不靜默燒 CPU。

---

*本指導書未變更程式碼、未 commit、未 push。Codex 可從 Wave M1 開始。前置提醒：請先確認本地已下載 ≥30 檔日線，否則雷達會（正確地）顯示資料不足。*
