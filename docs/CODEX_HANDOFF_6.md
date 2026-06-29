# CODEX_HANDOFF_6 — 關係層（跨源確認 + 可信度濾鏡）

> 給 Codex 的可直接執行指令。延續 HANDOFF_3（結構指紋，已上線）、HANDOFF_4（市場雷達）、HANDOFF_5（讀圖導覽）。
> **規則底線不變**：描述現在、教讀圖、**不預測、不給買賣訊號、不報明牌**。紅線測試擋下。
> 由 Claude 整理。本文件未 commit/未 push。
> **硬規則：本功能一律遵守 `CHART_VISUAL_PRINCIPLES.md`——文字用錨定泡泡長在圖上(不丟右下角)、能用圖就不用字、關係用圖示(箭頭/漏斗/霧化)而非純文字。**

---

## 0. 一句話

把目前手上**所有資料的「彼此關係」**算出來、用白話講出來、標到圖上。核心是一句小白也懂的問題：**「這次的漲跌，到底扎不扎實？」**（價、量、法人、新聞有沒有對上）。再用昨天的數學模型（結構指紋）當「**這檔好不好讀**」的可信度濾鏡。

---

## 1. 最重要的觀念：兩種「高度」，不可混為一談（鎖定）

| 高度 | 是什麼 | 資料 | 比喻 | 在本功能的角色 |
|---|---|---|---|---|
| **事件層（快）** | 最近幾天**發生了什麼、扎不扎實** | 價、量、法人、新聞、(基本面背景) | 天氣 | 主角：跨源確認 |
| **性格層（慢）** | 這檔**整體脾氣、好不好讀** | 結構指紋（延續性/複雜度/湍流/噪音色/波動聚集，HANDOFF_3 已有） | 氣候/地形 | **可信度濾鏡**：決定事件層的讀數「該信幾分」 |

- 性格層**不會「帶動」某根 K 棒**；它是背景，用來**打折/加權**事件層的解讀。
- 「結構指紋」是**描述這檔性格的數學鏡頭，不是猜未來的模型**。任何「猜測/預測未來」用語一律禁止（見 §7）。

---

## 2. 新模組 `app/analyze/relationships.py`（純 Python，重用既有資料，不新算指標基礎）

輸入：**既有 `build_stock_payload` 已備妥的資料**（prices/volume、institutional/chips、news 風險、structure、indicators、revenue/financial）。本模組只做「關係」的彙整與分類，**不重算 RSI/MACD 等基礎指標**（要用就讀 payload 裡算好的）。

輸出：`build_relationships_payload(payload) -> dict`，形狀見 §6。每個關係項：
```python
{
 "key": str, "group": str,           # confirm/derivation/progression/personality/experimental
 "label": str,                        # 對外白話名
 "narration": {"plain": str, "why": str, "detail": str},  # 真‧小白版三層（沿用 HANDOFF_5 §1.5）
 "forbidden": str,                    # 不得解讀為…
 "reliability": "high"|"medium"|"low",# 由性格層濾鏡給（見 §4）
 "targets": [ ... ]                   # 圖上要標什麼（沿用 HANDOFF_5 Target 型別）
}
```

---

## 3. 主角：跨源確認「這次漲跌扎不扎實」`cross_source_confirmation`

對「最近一日」與「最近 5 日」各算一次。比對三個來源**是否和價格同方向**：

- **價方向** `price_dir`：視窗報酬正負。
- **量支持** `volume_state`：最近量 vs 近20日均量 → 量增(≥1.2x)/正常/量縮(≤0.8x)。
- **法人方向** `inst_dir`：視窗內三大法人合計淨買賣超正負（無法人資料 → 該源標「無資料」，不參與計分）。

**對齊計分**（純描述）：可用來源中，有幾個和價格同方向 → `agree / total`（例：2/2、1/2）。

**白話分類（Layer 0，零數字零術語）**：
- 漲 + 量增 + 法人偏買：「這次上漲**有量、也有大戶同步**——比較扎實。」
- 漲 + 量縮 或 法人偏賣：「這次上漲**量縮(或大戶沒跟)**——比較虛，留意。」
- 跌 + 量增 + 法人偏賣：「這次下跌**有量、大戶也在賣**——是真的在跑。」
- 跌 + 量縮：「這次下跌**沒什麼量**——比較像惜售。」
- `forbidden`：「『扎實』**不代表會續漲**；只描述這次漲跌有沒有量和大戶撐。」
- `targets`：在最近那根/那幾根 K 上標記 + 量能柱閃 + (有法人則)法人方向小標。

> 這是整個功能的**門面**：把所有資料一次用上，回答小白最直覺的問題。

---

## 4. 可信度濾鏡：結構指紋 → `reliability`（鎖定用法）

讀 `payload["structure"]`（HANDOFF_3 的六維），導出一個**整體 readability**，套到上面每個關係項的 `reliability`：
- **複雜度高 / 湍流高 / 噪音偏白** → readability 低 → 關係讀數標 `reliability:"low"` + 文案加「這檔最近**很亂**，下面的判讀**參考就好**」。
- **延續性高 / 不太亂** → readability 高 → `reliability:"high"` + 「這檔最近**蠻好讀**，判讀**比較可信**」。
- 結構資料不足 → readability `medium`，不誇大。
- **導覽開場第一章**就先講這個 readability（「先看這檔好不好讀」），後面每段解說都帶著這個折扣。
- `forbidden`：readability 是「**多可信**」，不是「會漲會跌」。

---

## 5. 其餘關係群（次要，依序）

### 5.1 衍生鏈 `derivation`（最安全、最有「原來如此」）
靜態關係圖 + 現值，說明「這個是從那個算出來的」：
- MACD ＝ 兩條均線的距離（EMA12−EMA26）。
- 布林上下軌 ＝ 均線 ± 波動。
- KD ＝ 收盤在最近高低區間的位置。
圖上用**連線/箭頭**把「來源 → 衍生」連起來；Layer 0：「MACD 其實就是兩條均線拉開的距離。」
`forbidden`：只是說明算法關係，**不含任何方向判斷**。

### 5.2 階段 `progression`（你說的「漸進」）
- 均線**糾結→發散**：三條均線靠很近(方向不明) vs 散開(方向出來)。用既有 `ma*` 值算離散度。
- 布林**收斂→擴張**：用既有 `bb_width` 的近期相對高低。
Layer 0：「三條線現在**黏在一起**，方向還不明朗。」`forbidden`：不得當「要噴出/要變盤」。

### 5.3 新聞對齊 `news_align`（延後 R 後續；只做對齊，最克制）
> 本輪先不實作 `news_align`；保留為 R 後續，避免規格與本輪實作狀態不一致。

- **事件對齊**：最近的跳空/爆量/大波動那天，**附近有沒有新聞**（用既有 news 服務/risk matrix 的日期對齊）。Layer 0：「這天**特別會動**，當天附近有這幾則新聞。」
- **風險字眼**：近期是否出現下市/財務危機/交易限制等字（沿用既有 risk matrix）。
- `forbidden`：**不做**「利多所以漲」的情緒因果；只做「那天有事」的時間對齊。

### 5.4 基本面背景 `fundamental_ctx`（低頻、背景）
月營收 YoY、EPS/毛利趨勢、估值殖利率位階——一句背景，`forbidden`：不當買賣理由。

### 5.5 領先 / 背離 `lead_divergence`（**實驗層、預設關**）
- 量先價行、價與動能背離（RSI/MACD 與價不同調）。
- **只描述已發生**（「這裡出現背離了」），forward 一律條件句 + 配歷史情境扇形；放實驗分頁、強免責、標「實驗性」。本輪可只做偵測旗標、先不上主畫面。

---

## 6. API / 整合

- `build_relationships_payload(payload)`（純函數，吃既有 payload，不另打 DB、不重算基礎指標）。
- 併入 `build_stock_payload` → `"relationships"`；`try/except` 容錯，失敗 `{"available": False}`，不可拖垮個股頁。
- **接進讀圖導覽（HANDOFF_5）**：新增章節
  - 開場後加 `personality`（可信度濾鏡：這檔好不好讀）。
  - 新主章 `confirm`（跨源確認：這次漲跌扎不扎實）。
  - `derivation` / `progression` 視資料插入。
- 不需額外快取（隨個股 payload；結構快取已含）。

### 6.1 回傳形狀（示意）
```json
"relationships": {
  "available": true,
  "as_of_date": "2026-06-22",
  "readability": {"level":"high","plain":"這檔最近蠻好讀，判讀比較可信。"},
  "items": [
    {"key":"confirm_5d","group":"confirm","label":"這次上漲扎不扎實",
     "narration":{"plain":"這次上漲有量、大戶也偏買，比較扎實。",
                  "why":"老手會看漲勢背後有沒有量能和大戶同步。",
                  "detail":"5日報酬 +x%；量比 1.3；三大法人合計淨買 N 張。"},
     "forbidden":"『扎實』不代表會續漲。","reliability":"high",
     "targets":[{"type":"candles","dates":["..."]},{"type":"subplot","key":"volume"}]}
  ],
  "disclaimer":"資料關係描述 · 描述現在 · 不預測未來 · 非投資建議"
}
```

---

## 7. 紅線測試（強制，新增「猜測/預測」攔截）

新增 `tests/test_relationships_guardrails.py`：掃 `build_relationships_payload` 範例輸出 + 導覽含 relationships 的 HTML，不得出現：
```
會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊|前兆|
猜測|預測|預估會|未來會|接下來會漲|接下來會跌
Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price|forecast|predict
```
- 每個關係項 `forbidden` 非空。
- 「跨源確認」文案必為「扎不扎實/同不同方向」這類**描述**，不得含方向預測。
- Layer 0 lint（沿用 HANDOFF_5 §1.5.7）：`narration.plain` 不得含數字或術語縮寫。
- 缺資料（無法人/無新聞/結構不足）→ 該關係項標「無資料」或降 reliability，不丟例外。

---

## 8. 絕對不要做（Do-NOT）

- ❌ 不要把「扎實/同步/背離」寫成「會漲/會跌/該買賣」。
- ❌ 不要把結構指紋（性格層）當成方向訊號或預測模型——它只當**可信度濾鏡**。
- ❌ 不要做新聞情緒當訊號；新聞只做**事件對齊 + 風險字眼**。
- ❌ 不要在 relationships 裡重算 RSI/MACD/均線（讀 payload 既有值）。
- ❌ 領先/背離不得進主畫面（實驗層、預設關）。
- ❌ 不可拖垮個股頁（try/except）。
- ❌ 沒有合成/樣板資料測試的關係項不准合進 main。

---

## 9. 施工順序與驗收

```
Wave R1  relationships.py：跨源確認 confirm + readability 濾鏡（讀 structure）
         tests/test_relationships.py（合成：漲+量增+法人買→扎實；漲+量縮→虛；高複雜度→reliability low）
Wave R2  併入個股 payload "relationships" + 導覽新增 personality / confirm 章 + glossary 補詞
Wave R3  derivation 連線 + progression 階段 標到圖上
Wave R4  (實驗層, 預設關) lead_divergence 偵測旗標 + 強免責
```
最終：
```
[ ] python -m pytest -q 全綠（含 relationships 測試與紅線）
[ ] python -m compileall app ；node --check app/ui/static/(app.js|chart_tour.js)
[ ] 紅線含「猜測/預測」；每關係項 forbidden 非空；Layer 0 無數字無術語
[ ] 2330(資料齊) 顯示跨源確認+可信度；缺法人/缺新聞/結構不足 → 正確降級不報錯
[ ] relationships 不重算基礎指標、不拖垮個股頁
```
完成後 commit（建議：`Add relationship layer (cross-source confirmation + reliability filter)`），**先不要 push**，交回檢視。

---

## 10. 給 Codex 的提示

主角是「**這次漲跌扎不扎實**」——把價、量、法人放在一起比同方向，**只描述、不預測**；結構指紋只當「**這檔好不好讀**」的折扣。Layer 0 寫得像跟阿嬤解釋、數字滾去 Layer 2。先寫 `relationships.py` + 合成資料測試，再接導覽與圖上標記。

---

*本指導書未變更程式碼、未 commit、未 push。Codex 可從 Wave R1 開始。*
