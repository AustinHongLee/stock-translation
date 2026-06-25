# CODEX_HANDOFF_7 — 技術面推估（實驗室 / Forecast Lab）

> 給 Codex 的可直接執行指令。延續 HANDOFF_3/4/5/6 與 `CHART_VISUAL_PRINCIPLES.md`。
> 由 Claude 整理。本文件未 commit/未 push。
>
> ⚠️ **這是本專案唯一允許「給方向」的地方，且僅限實驗室。** 主產品的「描述、不預測」紅線**不變**；本功能是**獨立、預設關閉、強免責**的實驗區。

---

## 0. 一句話

在大型 K 線圖加一個**實驗室開關**：打開後，把 RSI/KD 等指標**畫進圖**、在價格右側畫出**未來情境扇形**、並給一個**技術面「偏多／偏空／中性」傾向**；旁邊**老實列出「只用了價格技術面，缺新聞、法人、風險」**與信心高低。**預設關、滿版免責、非投資建議。**

---

## 1. 硬界線（鎖定，Codex 不可放寬）

1. **預設關閉 + 一次性免責**：實驗室預設不顯示；第一次開啟跳一次 modal「這是技術面推估實驗，只用價格資料，常常會錯，非投資建議」，使用者確認後才進。
2. **只給「傾向」，不給「動作」**：可輸出 `偏多 / 偏空 / 中性` 傾向與「歷史上類似情況偏多的比例」。**嚴禁**：目標價、買進/賣出點、停損停利、保證、必漲/必跌、All in/梭哈。
3. **永遠帶限制欄**：每次輸出都要附「**此推估只用價格技術面；缺新聞、法人、風險，僅供參考**」+ 信心等級。
4. **資料缺 → 信心強制下修**：新聞或法人資料缺、或結構複雜度高 → 信心最高只能到 `medium`，並明列缺哪些。
5. **隔離**：獨立模組 `forecast_lab.py`、獨立 API、獨立 UI 區塊；**不進**主個股摘要、不進報告/匯出、不污染既有 `relationships`/結構卡。主產品紅線測試**原封不動**。
6. **不引入 numpy/scipy**；不重算基礎指標（讀既有 `features.latest` / `historical_frequency`）。

---

## 2. 模組 `app/analyze/forecast_lab.py`（純 Python）

`build_forecast_lab(payload) -> dict`，吃既有個股 payload（features / historical_frequency / structure / chips_series / news）。

### 2.1 技術面傾向分數（透明加權，可測；沿用 `scores.py` 風格）
讀 `features.latest`，每項給 ±權重，加總正規化到 −100..+100：
| 輸入 | 規則（範例權重，Codex 可微調但要寫在常數） |
|---|---|
| 均線排列 | ma5>ma20>ma60 → +30；反向 → −30 |
| 價 vs 月線(乖離) | 收盤>ma20 → +10；< → −10 |
| MACD 柱 | >0 → +15；<0 → −15 |
| KD | k>d 且 k<80 → +15；k<d → −15；k≥80 → −5(過熱) |
| RSI | 55–70 → +10；30–45 → −10；>75 → −5；<25 → +5(超賣) |
| 動能 ROC20 | 正 → +10；負 → −10 |
- `lean_score = clamp(sum, -100, 100)`；`lean = 偏多(≥+25) / 中性 / 偏空(≤−25)`。
- 必須回傳 **contributing factors 清單**（哪幾項推向哪邊），讓使用者看得到「為什麼」。

### 2.2 未來情境扇形（重用歷史頻率，非單一線）
- 取 `historical_frequency` 對「目前最相符事件」的前向報酬分布 p10/p50/p90（5 日、20 日）。
- 由最後收盤畫**會張開的範圍帶**（外 p10–p90、中位 p50）。**不畫單一保證線。**
- 樣本不足 → 不畫中位、只畫範圍 + 標「樣本少」。

### 2.3 信心 / 限制（核心,你要的「缺什麼」）
```
confidence 起點 = relationship_readability(structure).level   # high/medium/low（重用 HANDOFF_6）
若 news 缺 → 加註「缺新聞風險」、confidence 上限 medium
若 chips_series 缺 → 加註「缺法人」、confidence 上限 medium
最終一律附固定句：「此推估只用價格技術面，缺新聞、法人、風險，僅供參考。」
```

### 2.4 回傳形狀
```json
"forecast_lab": {
  "available": true,
  "experimental": true,
  "lean": "偏多",                    // 偏多 / 中性 / 偏空
  "lean_score": 38,                  // -100..100（細節層才顯示數字）
  "factors": [{"label":"均線排列","dir":"+"}, {"label":"MACD柱","dir":"+"}, ...],
  "scenario": {"d5":{"lo":-4.9,"mid":0.1,"hi":6.2,"count":23}, "d20":{...}},
  "history_bullish_ratio": 0.57,     // 「過去類似情況偏多的比例」(描述歷史)
  "confidence": "low",
  "missing": ["新聞","法人風險"],
  "limitations": "此推估只用價格技術面，缺新聞、法人、風險，僅供參考。",
  "disclaimer": "技術面推估實驗 · 只用價格資料 · 常常會錯 · 非投資建議"
}
```

### 2.5 合成資料黃金測試（`tests/test_forecast_lab.py`，合併門檻）
- 全多頭輸入(ma多排+MACD>0+KD金叉+RSI 60) → `lean=="偏多"` 且 `lean_score>25`。
- 全空頭輸入 → `lean=="偏空"`。
- 混合/中性 → `中性`。
- news 缺 / chips 缺 → `confidence` ≤ medium 且 `missing` 含對應項。
- 歷史不足 → scenario 無中位、不丟例外。

---

## 3. API

- `GET /api/stocks/{id}/forecast-lab`（**獨立端點**，預設前端不自動打，使用者開實驗室才打）。或併入 payload 但加 `experimental:true` 且前端預設不顯示。
- 容錯：失敗回 `{"available": False}`，不可影響個股頁。
- 不需重算；可快取(key 含 last_close_date)。

---

## 4. 前端：實驗室 UI（大型圖內，預設關）

- 大型圖工具列加按鈕「**技術面推估（實驗）**」，旁標小字「實驗·非建議」。
- 第一次點 → 一次性免責 modal（§1.1），確認後才啟用。
- 啟用後在圖上：
  1. **指標畫進圖**：RSI/KD 的超買/超賣區用淡色帶標在副圖、MACD 金叉/死叉點標記（重用既有 subplot/featureSeries）。
  2. **未來情境扇形**：價格右側畫範圍帶（重用既有 scenario cone 繪法），**虛線、低彩度、明確「推估區、非保證」**。
  3. **傾向徽章**：`偏多/偏空/中性` + 點開看 `factors`（為什麼）與 `lean_score`（細節層才出數字）。**禁紅綠當方向**（用形狀/圖示 + 中性色 + 文字）。
  4. **限制／信心欄**(常駐)：列 `missing`、`confidence`、`limitations`。
- 頂部**常駐免責橫幅**(disclaimer)；整區加「實驗」浮水印或邊框,跟主畫面明顯區隔。
- 關掉實驗室 → 圖回到一般狀態。

---

## 5. 文案規則（白話三層 + 實驗區紅線）

- Layer 0（傾向徽章與一句話）零術語零數字：「技術面看起來**偏多一點**(只看價格,參考就好)。」數字/指標名放點開的細節層。
- **實驗區允許**：偏多/偏空/中性、技術面傾向、歷史上偏多比例 X%、推估區間。
- **實驗區仍禁**(寫進測試)：`目標價|買進|賣出|買賣點|停損|停利|保證|必漲|必跌|All ?in|梭哈|Target|Buy|Sell|包賺|穩賺`。
- 每次輸出必含 `limitations`(缺新聞/法人/風險) 與 `disclaimer`,否則測試失敗。

---

## 6. 紅線測試

新增 `tests/test_forecast_lab_guardrails.py`：
- 掃 `build_forecast_lab` 範例輸出 + 實驗室 HTML，不得出現 §5 禁字。
- `lean` 只能是 {偏多,中性,偏空}；必含 `limitations`、`disclaimer`、`experimental:true`。
- **主產品紅線測試不得改動**(確認實驗室文案沒洩漏進主個股頁/報告)：加一條測試 `build_stock_payload` 預設輸出**不含** forecast_lab 的方向字眼(除非實驗端點)。

---

## 7. 絕對不要做（Do-NOT）

- ❌ 不要給目標價、買賣點、停損停利、保證、必漲必跌。
- ❌ 不要預設開啟、不要進主摘要/報告/匯出。
- ❌ 不要畫單一「未來保證線」(只畫會張開的範圍帶)。
- ❌ 不要用紅綠色表方向。
- ❌ 不要因為實驗室就放寬**主產品**的紅線測試。
- ❌ 不要黑箱:傾向一定要附 contributing factors。

---

## 8. 施工順序與驗收

```
Wave F1  forecast_lab.py：透明傾向分數 + 信心/限制 + 重用情境扇形
         tests/test_forecast_lab.py（合成黃金測試全綠）
Wave F2  /api/stocks/{id}/forecast-lab（獨立、容錯、快取）
Wave F3  實驗室 UI：工具列按鈕 + 一次性免責 modal + 圖上指標/扇形/傾向徽章/限制欄 + 常駐免責
Wave F4  tests/test_forecast_lab_guardrails.py + 主產品未洩漏測試
```
最終：
```
[ ] python -m pytest -q 全綠（含 forecast_lab 與 guardrails；主產品既有測試不變紅）
[ ] node --check app/ui/static/(app.js|chart_tour.js|forecast_lab.js)
[ ] 預設關閉；開啟需一次性免責；關掉可復原
[ ] 每次輸出含 limitations(缺新聞/法人/風險)+disclaimer；lean∈{偏多,中性,偏空}
[ ] 無目標價/買賣點/保證字眼；傾向附 factors；扇形為範圍非單線
[ ] 主個股頁/報告 預設不含方向字眼
```
完成後 commit（建議：`Add experimental technical forecast lab`），**先不要 push**，交回檢視。

---

## 9. 給 Codex 的提示

傾向分數要**透明、可在合成資料上驗證**(全多頭→偏多)、附 factors;未來只畫**會張開的範圍帶**;限制欄是這功能的良心,永遠在。先寫 `forecast_lab.py` + 合成測試,再做獨立 API,最後做預設關、強免責的 UI。記住:**這裡可以報傾向,但永遠不報買賣與目標價。**

---

*本指導書未變更程式碼、未 commit、未 push。Codex 可從 Wave F1 開始。*
