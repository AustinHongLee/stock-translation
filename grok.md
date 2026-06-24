# 市場即心智 — Grok 審閱與實作建議

> 審閱對象：`MARKET_AS_MIND_SPEC.md`（2026-06-24）
> 立場：本文件只做規劃與意見，**未改 code、未 commit、未 push**。
> 讀者：你、Codex、以及之後接手的工程代理。

---

## 0. 一句話結論

**這份規格的方向是對的，而且跟「股票翻譯機」的紅線高度一致**——描述現在、不預測未來、資料不足就說不足。建議照 §10 的務實版做 MVP（6 個 D0/A 描述子 + 結構指紋卡），但要在**命名、引擎整合、UI 呈現**三處跟現有架構對齊，否則會變成第四套平行系統，維護成本爆炸。

---

## 1. 我認為規格寫得很好的地方

### 1.1 雙軸分類解決了真正的設計矛盾

§0 把「需要什麼資料（D0/D1/D2）」和「能不能上線（A/B/C/D）」拆成**正交標籤**，這比混在一張表裡聰明得多。工程上可以直接用：

```
可上線 = DataTier ≤ 目前資料能力 AND MaturityTier ≤ 目前產品層級
MVP    = D0 ∩ A
```

這讓「想做的酷東西」和「現在能負責任交付的東西」不會互相綁架。

### 1.2 「描述而非預測」是差異化，不是退讓

台股 App 滿街都是「突破買進」「目標價」「勝率」。你已有 `CODEX_HANDOFF` 紅線、`range_stats` 的「只描述選取區間」、`historical_frequency` 的「歷史範圍非預測」——**結構指紋是同一條產品哲學的延伸**，不是新方向。對有投資人的產品來說，「誠實」比「聽起來很厲害」更值錢。

### 1.3 MVP 選指標的標準正確

§6 挑的 6+1 個指標符合四個條件：**只要 OHLCV、文獻成熟、可在合成資料驗證、白話可講**。這跟 `CODEX_HANDOFF_2` 要求的「黃金測試」完全合拍——Hurst/PE 在白噪音與 fBm 上都有已知對照值，比很多「AI 評分」好測一百倍。

### 1.4 免責設計 §9 不是裝飾

每指標的「白話解讀」+「不得解讀為」+ 充足度徽章 + Tier C/D 閘門——這套如果做紮實，能擋住散戶把 Hurst 當動量訊號、把雪崩冪律當崩盤預告的衝動。**建議把 §9 當驗收條款，不是文案建議。**

### 1.5 Phase 切割合理

Phase 1（單股指紋）→ Phase 2（市場雷達，要 D1 橫截面）→ Phase 3（研究實驗室）的順序跟現有資料能力一致：你已有 `SQLiteStore` 日線、法人、財報，但**還沒有**穩定的「≥30 檔同步橫截面載入器」——Phase 2 依賴這個，不能跳。

---

## 2. 需要調整或注意的意見

### 2.1 🔴 命名：學術感太強，違反「翻譯機」初衷

規格標題「市場即心智」「量子認知」「信念場」對研究有趣，但**對散戶是障礙**。`UX_DESIGN_翻譯機.md` 已明講：先講人話，圖當配角。

| 規格用語 | 建議對外名稱 | 理由 |
|---|---|---|
| 市場即心智 / Structure Fingerprint Lab | **結構指紋** | 具體、不玄 |
| 記憶性（Hurst H） | **慣性程度** 或 **延續性** | H>0.5 不是「會漲」 |
| 湍流程度（Δα） | **波動結構複雜度** | 「湍流」聯想颱風 |
| 臨界傾向 | **極端波動傾向** | 避開「快爆了」聯想 |
| 市場心智雷達 | **市場結構雷達** | 「心智」暗示能讀心 |
| Tier D 量子定價等 | **不進 UI**（規格已寫，堅持） | 誤導風險極高 |

**內部** module/key 可用 `structure_*`；**使用者看到的**一律走翻譯表（建議 `structure_registry.py`，見 §4）。

### 2.2 🔴 不要變成第四套引擎

現有架構已有清晰分工：

| 模組 | 職責 |
|---|---|
| `indicators.py` + `indicator_registry.py` | K 線圖 ~150 個 OHLCV 特徵，registry 驅動 UI |
| `vital_signs.py` | 財報/營收體質卡（非價格） |
| `range_stats.py` / `historical_frequency.py` | 區間統計、歷史情境（描述性） |

規格建議的 `structure_metrics.py` **應該存在**，但定位要清楚：

- ✅ **獨立引擎**：演算法與 `indicators.py` 不同（DFA、熵、譜分析），獨立檔案合理。
- ❌ **不要**把 6 個結構指標全部塞進 `indicator_registry` 當 subplot——它們的呈現是「六維指紋卡」，不是 K 線疊線。
- ✅ **要**共用底層：`log returns` 抽取、暖身棒、`{value, confidence, available, reason}` 回傳格式，跟 `FeatureBundle` 風格對齊。
- ✅ **要**掛進 glossary：`app/glossary/service.py` 為每個維度加「四句翻譯卡」條目。

### 2.3 🟠 與現有指標的重疊要說清楚

使用者會問：「你已有 HV20、ATR、趨勢強度，為什麼還要結構指紋？」

| 結構維度 | 現有近似 | 差異（要在 UI 講清楚） |
|---|---|---|
| 湍流（RV 百分位） | `hv_20` / `hv_60` 副圖 | 百分位回答「跟**自己歷史**比有多亂」，不是絕對波動率 |
| 波動聚集 | HV 序列目視 | 自相關指數，量化「大波後是否常接大波」 |
| 記憶性 Hurst | `trend_strength` (ADX) | ADX=趨勢**強度**；Hurst=序列**自相關結構**，不是方向 |
| 複雜度 PE/SampEn | 無 | 真正新增價值，應在指紋卡**置頂強調** |

指紋卡每維 hover 加一句：「這跟圖上的 XX 不同，因為……」可減少「又來一套指標」的疲勞。

### 2.4 🟠 資料長度現實：台股新股會大量灰掉

| 指標 | 最小 N | 台股現實 |
|---|---|---|
| Hurst DFA | 120（穩：250） | 多數上市股 OK |
| MFDFA Δα | 500 | 新股、剛掛牌常不達標 → 規格已寫灰掉，**要常態化** |
| SampEn | 200 | 勉強可算 |
| Spectral β | 256 | 邊緣 |

建議 API 回傳 `data_sufficiency: {bars_available, bars_recommended, grade: "high"|"medium"|"low"|"insufficient"}`，前端用灰階/虛線，不要顯示假精確的小數。

### 2.5 🟠 效能與快取

- `sample_entropy` 是 O(N²)——單股、單次還好；若未來想掛「全市場結構排行」，必須快取。
- 規格寫的 key=`stock_id+last_date+window` 正確；建議沿用 `app_cache` 表（`CODEX_HANDOFF_2` 已引入），TTL 可設 24h 或跟著日線更新失效。
- **Phase 1 不要**對 `/api/local-data` 全市場逐檔算結構——會拖垮已優化過的 local-data cache。

### 2.6 🟡 「六維長條 0–5 格」需要標準化函式

規格畫了 `■■■■□□` 但沒定義**怎麼把連續值映到 0–5**。建議：

```python
# 每維各自定義 monotonic map + clamp，寫死在 structure_registry
# 例：hurst_h → 0.5 為中心，[0.35, 0.65] 線性映射到 [0, 5]
# 輸出同時保留 raw_value + bar_level + bar_level_label
```

避免工程師各自用 percentile 或 z-score，導致 A 股 B 股尺度不一致。

### 2.7 🟡 紅線掃描要擴充

`CODEX_HANDOFF_2` 禁字表應加上結構層專用：

```
會漲|會跌|該買|該賣|目標價|勝率|機率|崩盤預告|快崩|買進訊號|賣出訊號
```

雪崩/臨界類 UI 強制帶「**非預告**」尾綴——寫進測試（類似現有紅線 grep 驗收）。

### 2.8 🟢 Tier B/C/D 的處理：同意規格，再加一條

- **B（RQA、TDA、Lyapunov）**：只進「研究實驗室」分頁，預設關，URL 可深連結但進場要一次免責。
- **C（敘事 proxy）**：若用 OHLCV proxy，UI 必須標 **「假設性代理，非真實輿情」**——比 Tier A 多一層視覺降權。
- **D（量子/Hopfield）**：**永不進產品**；可留學術筆記在 `docs/`，不進 `app/`。

---

## 3. 與現有產品架構的整合建議

### 3.1 放哪裡（UI 資訊架構）

建議掛在**個股頁**，位置順序：

```
Header（代號/名稱）
  ↓
估值/體質區（既有）
  ↓
【新增】結構指紋卡  ← Phase 1 主角
  ↓
K 線大圖 + 指標資料室（既有）
  ↓
籌碼/新聞/報告（既有）
```

理由：指紋卡是「這檔股票現在的性格」，跟估值/體質同層級的「翻譯」；不要塞進 K 線資料室（那裡已經夠擠，`app.js` 6000+ 行）。

市場結構雷達（Phase 2）放**雷達中心**新分頁，跟「收盤快照排行」並列，不要取代現有排行。

### 3.2 API 設計

規格寫 `GET /api/stocks/{id}/structure`——可以，但 Phase 1 也可先併入既有 stock payload 的 `structure_fingerprint` 欄位，減少前端來回。若計算變重再拆 endpoint。

建議回傳形狀：

```json
{
  "available": true,
  "as_of_date": "2026-06-22",
  "disclaimer": "結構描述工具 · 描述現在 · 不預測未來 · 非投資建議",
  "sufficiency": {"bars": 365, "grade": "high"},
  "dimensions": [
    {
      "key": "memory",
      "label": "慣性程度",
      "bar_level": 4,
      "bar_max": 5,
      "raw": {"hurst_h": 0.58, "dfa_r2": 0.91},
      "confidence": "high",
      "summary": "近期行為偏向延續，不是隨機亂走。",
      "do_not": "不得解讀為會繼續漲或一定反轉。",
      "method": "DFA-1 on log returns, window=250"
    }
  ]
}
```

### 3.3 測試策略（對齊 HANDOFF_2）

`tests/test_structure_metrics.py` 必須包含：

| 測試類型 | 輸入 | 預期 |
|---|---|---|
| 白噪音 | i.i.d. Gaussian returns | H ≈ 0.5 ± 0.05，PE ≈ 1.0 |
| fBm 合成 | 已知 H=0.7 | DFA 斜率 ≈ 0.7 ± 0.08 |
| 正弦+噪音 | 低頻主導 | β 偏粉紅（0.8–1.2 區間） |
| 短序列 | N=50 | `available=false`，reason 明確 |
| 平盤 tie | 連續相同 close | PE 不 crash，tie 規則生效 |
| 壞資料 | close=0 / null | 不污染，回傳 reason |

**沒有合成資料黃金測試就不該合進 main。**

### 3.4 報告匯出

Phase 1 尾聲併入 `html_report.py` / Excel 匯出：指紋卡簡化版（六維文字 + 充足度），跟體質卡並列。

---

## 4. 建議新增檔案（Phase 1 最小集）

```
app/analyze/structure_metrics.py    # 純函數計算
app/analyze/structure_registry.py   # 六維 metadata、映射、白話、禁止解讀
app/analyze/structure_report.py     # 組裝 StructureFingerprint payload
tests/test_structure_metrics.py     # 黃金測試
tests/test_structure_report.py      # 整合 + 充足度降級
```

**不要動** `indicators.py` 主流程（除非抽共用 `log_returns_from_prices()` 到 `app/analyze/price_series.py` 之類的小模組——可選，非必須）。

前端：

```
app/ui/static/structure_card.js   # 若 app.js 已太大，獨立小檔
# 或在 app.js 加一區 // --- Structure Fingerprint Card ---，二選一
```

---

## 5. 施工順序（建議給 Codex 的 Wave 計畫）

### Wave S1 — 引擎 + 測試（不碰 UI）

- [ ] `structure_metrics.py`：6 個函式（Hurst DFA、PermEn、SampEn、Spectral β、VolClustering、RV percentile）
- [ ] `structure_registry.py`：六維映射與文案
- [ ] `test_structure_metrics.py`：合成資料黃金測試全過
- [ ] 可選：`multifractal_width()` 僅在 N≥500 時啟用
- **驗收**：`python -m pytest tests/test_structure_metrics.py` 全綠；`python -m compileall app`

### Wave S2 — API + 個股指紋卡

- [ ] `structure_report.py` + API 欄位或 `/structure` endpoint
- [ ] 個股頁指紋卡 UI（六長條 + hover 四句 + 充足度徽章 + 頂部免責）
- [ ] glossary 條目補六維
- [ ] 紅線掃描擴充字表
- **驗收**：`pytest` 全綠；`node --check`；瀏覽器 smoke 兩檔（長歷史 2330 + 短歷史新股）

### Wave S3 — 報告 + 快取

- [ ] HTML/Excel 匯出指紋卡
- [ ] `app_cache` 快取結構 payload
- [ ] 文件：`docs/structure-fingerprint.md` 方法說明（給進階使用者）
- **驗收**：匯出檔案含免責；快取命中不重算

### Wave S4 — 市場結構雷達（Phase 2，前置：橫截面載入器）

- [ ] `cross_section.py`：對齊 ≥30 檔 returns matrix
- [ ] dispersion、平均相關、Kuramoto r
- [ ] 雷達中心新分頁
- **驗收**：模擬 Kuramoto 模型 r 已知時誤差在容忍內

### 不做（除非明確點名）

- Tier D 量子/Hopfield/集體意識
- Phase 3 敘事層 OHLCV proxy 上主 UI
- 全市場結構排行（需先解決 SampEn 快取與批次成本）

---

## 6. 風險登錄（簡表）

| 風險 | 嚴重度 | 緩解 |
|---|---|---|
| 使用者把 Hurst 當多空訊號 | 高 | 「不得解讀為」+ 色票不用紅綠 + glossary |
| 學術命名嚇跑散戶 | 中 | 對外翻譯表（§2.1） |
| app.js 再膨脹 | 中 | 獨立 `structure_card.js` 或分區嚴格隔離 |
| 新股全灰造成「壞掉感」 | 中 | 充足度文案：「歷史較短，僅顯示可算維度」 |
| SampEn 全市場算太慢 | 低（Phase 1） | Phase 1 僅單股；快取留到 Phase 3 |
| 跟 CHART 指標庫混淆 | 中 | 不進 indicator_registry；UI 分區 |

---

## 7. 跟規格 §10 的對照：我同意「留什麼、砍什麼」

**完全同意上線：**

- 6 個 D0/A 描述子 + 可選 MFDFA（N≥500）
- 結構指紋卡 + 免責 + 充足度
- 獨立 `structure_metrics.py`

**完全同意延後：**

- 市場雷達（D1）
- 雪崩冪律 / RQA / TDA / Lyapunov
- 敘事層 / Tier C/D

**我加的條件（相對原規格）：**

1. 對外改名「結構指紋」，不用「市場即心智」當主標題
2. 用 `structure_registry.py`，不塞進 chart registry
3. 合成資料黃金測試為合併門檻
4. Phase 1 不算全市場、不掛進 local-data bulk

---

## 8. 給你的決策問題（實作前請拍板）

1. **指紋卡預設展開還是收合？** 建議預設展開（這是差異化賣點），但可收合。
2. **計算視窗 W 預設多少？** 規格多處寫 250；建議預設 250 交易日、進階可選 120/500。
3. **MFDFA 要不要進 Wave S1？** 建議 Wave S1 先做 6 個穩的，MFDFA 當 S1.5 加分項。
4. **API 獨立 endpoint 還是併入 stock payload？** 建議先併入，重了就拆。
5. **要不要做「結構指紋歷史趨勢」小 sparkline？** 規格提滾動序列；MVP 可只做最新快照，sparkline 放 Wave S3。

---

## 9. 最終評價

| 維度 | 評分 | 說明 |
|---|---|---|
| 產品契合度 | ★★★★★ | 跟翻譯機紅線、體質卡、歷史情境同一語言 |
| 工程可行性（Phase 1） | ★★★★☆ | OHLCV 夠用；要注意 SampEn 與映射標準化 |
| 工程可行性（Phase 2+） | ★★★☆☆ | 橫截面載入器是硬依賴；B 級指標解釋成本高 |
| 使用者價值 | ★★★★☆ | 散戶少見的描述層；命名翻譯好可再 +半星 |
| 維護成本 | ★★★★☆ | 若堅持獨立引擎 + registry、不污染 indicators，可控 |
| 「酷」的程度 | ★★★★☆ | 學術味適度；砍掉 Tier D 反而更酷（克制） |

**總結**：這是值得做的「酷東西」，而且剛好補上你產品裡「技術指標很多、但缺少更高層結構描述」的洞。照規格 §10 的克制版落地，再套上 §2 的命名與整合建議，會是一個能長期演化的功能，而不是一個會被投資人問「這是不是在報明牌」的風險點。

---

*下一步：你拍板 §8 五個問題後，可用 `/implement` 或 `CODEX_HANDOFF_3.md` 開 Wave S1。*