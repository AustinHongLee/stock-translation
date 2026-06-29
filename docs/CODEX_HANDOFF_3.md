# CODEX_HANDOFF_3 — 結構指紋（Structure Fingerprint）實作指導書

> 給 Codex 的可直接執行指令。**所有設計決策已鎖定，不要再重新討論命名或位置**——照本文件做即可。
> 本文件由 Claude 整理（綜合 `MARKET_AS_MIND_SPEC.md` + `grok.md` + `deepseek.md` 的裁決）。
> 規則底線：這是**結構描述工具，描述現在、不預測未來、不給買賣訊號**。違反者單元測試擋下。

---

## 0. 你（Codex）要做什麼（一句話）

把「已經寫好且測試通過的數值引擎」接上產品：建 **registry → API 欄位 → 個股頁頂部指紋卡 → 報告/快取**。**不要新增任何理論、不要動演算法數學、不要碰 K 線圖那套 indicators 系統。**

---

## 1. 已經完成、請勿重做

| 檔案 | 狀態 | 說明 |
|---|---|---|
| `app/analyze/structure_metrics.py` | ✅ 完成且驗證 | 純 Python（零 numpy/scipy）。6 個估計子 + `MetricSnapshot` + `build_structure_fingerprint()` + `confidence_grade()`。 |
| `tests/test_structure_metrics.py` | ✅ 12/12 通過 | 合成資料黃金測試（白噪音 H≈0.5、隨機漫步 H≈1.5、白噪音 β≈0、隨機漫步 β≈2、短序列降級…）。 |

可直接呼叫的介面（**不要改簽名**）：

```python
from app.analyze.structure_metrics import (
    build_structure_fingerprint,   # (closes: Sequence[float]) -> dict
    confidence_grade,              # (MetricSnapshot) -> "high"|"medium"|"low"|"insufficient"
    hurst_dfa, permutation_entropy, sample_entropy,
    spectral_slope, volatility_clustering, realized_vol_percentile,
    MetricSnapshot, DISCLAIMER,
)
```

`build_structure_fingerprint(closes)` 目前回傳：
```python
{
  "available": bool,
  "return_count": int,
  "dimensions": [ {"key","label","source","level"(0-5|None),"grade","snapshot"{...}} , ... 共5維],
  "metrics": { "<key>": {value,available,confidence,reason,reading,forbidden}, ... },
  "synchrony_locked": True,
  "disclaimer": "...",
}
```
SampEn 不在 `dimensions`（卡片只用 PE 當複雜度），但 `sample_entropy()` 函式保留供進階/未來使用。

---

## 2. 已鎖定的決策（不要再問、不要改）

1. **命名**：個股卡叫「**結構指紋**」；六維對外用**白話 label**（見 §3）。「市場心智 / 市場即心智」這個有記憶點的名字**保留給未來的大盤雷達（Phase 2）**，個股階段不要用。
2. **維度 label（對外）**：`延續性`、`複雜度`、`波動聚集`、`噪音色`、`湍流程度`、`同步性(鎖定)`。**絕不用「記憶性」**（會被當「會續漲」）。
3. **SampEn 不進卡片**：複雜度只用 PE。
4. **卡片位置**：個股頁**頂部摘要區**（跟股價/漲跌/體質燈號同層），**不要**放在 K 線圖前面當「閘門」。
5. **計算視窗**：預設 **250** 個交易日。
6. **MFDFA（Δα）本輪不做**：未來做時 N≥1000 才顯示、標「實驗性」。
7. **registry 先於 API**：使用者看到的文案/映射集中在 `structure_registry.py`，前端與 API 一律讀它，不得在 JS/後端寫死。
8. **效能**：結果用 `app_cache` 快取；**嚴禁**在 `/api/local-data` 全市場批次裡逐檔算結構。

---

## 3. Wave S1 — `app/analyze/structure_registry.py`（先做這個）

**目的**：集中六維的對外 metadata、0–5 映射、白話文案、禁止解讀、與既有指標的差異說明、glossary 連結。引擎只出數字，文案全在這裡。

### 3.1 資料結構

```python
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True, slots=True)
class DimensionSpec:
    key: str            # memory/complexity/agitation/chroma/turbulence/synchrony
    source: str         # structure_metrics 的指標 key（synchrony 為 ""）
    label: str          # 對外白話名
    bar_lo: float       # 0 格對應值
    bar_hi: float       # 5 格對應值
    forbidden: str      # 不得解讀為…
    overlap_note: str   # 跟圖上既有指標的差異（hover 用）
    glossary_term: str  # 連到名詞小教室的詞
    locked: bool = False
```

### 3.2 六維內容（照抄）

| key | label | source | bar_lo→bar_hi | forbidden | overlap_note |
|---|---|---|---|---|---|
| memory | 延續性 | hurst_dfa | 0.3 → 1.0 | 不得解讀為會繼續漲或一定反轉；延續性描述自相關結構，不含方向。 | 與圖上「趨勢強度 ADX」不同：ADX 講趨勢強弱，延續性講序列的自相關結構。 |
| complexity | 複雜度 | permutation_entropy | 0.4 → 1.0 | 低複雜度 ≠ 可預測或可獲利。 | 圖上沒有對應指標，這是新增的描述維度。 |
| agitation | 波動聚集 | volatility_clustering | 0.0 → 3.0 | 不得解讀為即將大漲大跌；只描述波動的聚集性。 | 與 HV20/ATR 不同：這量化「大波是否成群出現」，不是波動絕對值。 |
| chroma | 噪音色 | spectral_slope | 0.0 → 2.0 | 不得當週期或轉折預告。 | 描述「波動的顏色」（白/粉紅/紅），不是方向或週期。 |
| turbulence | 湍流程度 | realized_vol_percentile | 0.0 → 100.0 | 高波動 ≠ 會跌；只描述目前波動相對自身歷史的位置。 | 這是 HV 的「歷史百分位」（跟自己比），不是絕對波動率。 |
| synchrony | 同步性 | (空) | — | 需要跨股資料；Phase 2 才開放。 | 個股看不到同步性，要看市場層級雷達。 | locked=True |

### 3.3 規則函式（registry 內）

```python
def bar_level(spec: DimensionSpec, value: float | None) -> int | None:
    if value is None: return None
    if spec.bar_hi <= spec.bar_lo: return 0
    ratio = (value - spec.bar_lo) / (spec.bar_hi - spec.bar_lo)
    return max(0, min(5, round(ratio * 5)))

# 白話 summary 由 structure_metrics 的 snapshot.reading 直接帶（已是白話），
# registry 只負責 label / forbidden / overlap / bar 映射 / glossary。
# 注意：snapshot.reading 內已不含「會漲/會跌」字眼，但 §7 紅線測試仍會掃。
```

### 3.4 充足度（data_sufficiency）

```python
RECOMMENDED_BARS = {           # 各維「建議」最小棒數（穩定門檻）
    "hurst_dfa": 250, "permutation_entropy": 120,
    "volatility_clustering": 150, "spectral_slope": 256,
    "realized_vol_percentile": 60,
}
def sufficiency_grade(bars_available: int) -> str:
    # 以最嚴格維度(256)為基準的整體等級
    if bars_available >= 256: return "high"
    if bars_available >= 150: return "medium"
    if bars_available >= 120: return "low"
    return "insufficient"
```

### 3.5 組裝函式（registry 或新 `structure_report.py` 皆可，建議放 registry）

`build_structure_payload(closes) -> dict`：呼叫 `build_structure_fingerprint(closes)`，套上 registry 的 label/bar_level/forbidden/overlap/grade/sufficiency，輸出 §4 的 API 形狀。

### 3.6 Wave S1 驗收

- `tests/test_structure_registry.py`：
  - 每維 `bar_level` 邊界（lo→0、hi→5、超出 clamp）。
  - `build_structure_payload` 對長序列回 6 維（synchrony locked）、對 N=50 全部降級且不丟例外。
  - 輸出不含 §7 任何紅線字。
- `python -m pytest tests/test_structure_metrics.py tests/test_structure_registry.py -q` 全綠。
- `python -m compileall app`。

---

## 4. Wave S2 — API + 個股頁指紋卡

### 4.1 API 契約（照此輸出）

把結構併入既有 `build_stock_payload()` 回傳 dict，新增 `"structure"` 鍵（放在 `valuation` 旁）：

```json
"structure": {
  "available": true,
  "as_of_date": "2026-06-22",
  "window": 250,
  "title": "結構指紋",
  "subtitle": "這檔股票現在的性格（結構描述，非預測）",
  "disclaimer": "結構描述工具 · 描述現在 · 不預測未來 · 非投資建議",
  "sufficiency": {"bars_available": 365, "grade": "high"},
  "synchrony_locked": true,
  "dimensions": [
    {
      "key": "memory",
      "label": "延續性",
      "bar_level": 4,
      "bar_max": 5,
      "grade": "high",
      "summary": "H=0.58：延續性偏高，傾向延續近期行為。",
      "forbidden": "不得解讀為會繼續漲或一定反轉；延續性描述自相關結構，不含方向。",
      "overlap_note": "與圖上『趨勢強度 ADX』不同：ADX 講趨勢強弱，延續性講序列的自相關結構。",
      "raw": {"hurst_dfa": 0.58, "dfa_r2": 0.91},
      "method": "DFA-1 on log returns, window=250",
      "glossary_term": "延續性"
    }
    // ... 其餘 4 維；synchrony 維輸出 {"key":"synchrony","label":"同步性","locked":true,...}
  ]
}
```

### 4.2 整合點

- 在 `app/web/api.py` 的 `build_stock_payload()`：用收盤序列（用既有 `valuation_prices` 或 `prices` 的 close，取最近 `window=250`）算 `build_structure_payload()`，塞進回傳 dict 的 `"structure"`。
- **失敗不可拖垮個股頁**：包 `try/except`，例外時 `"structure": {"available": False, "reason": "..."}`（比照 `valuation_payload["bands"]` 的容錯寫法）。

### 4.3 快取（必做）

- 用既有 `store.get_json_cache(key)` / `store.set_json_cache(key, payload)`。
- key：`f"structure::{stock_id}::{last_close_date}::{window}"`（含最後收盤日 → 新資料自動換 key、自動失效）。
- **嚴禁**在 `build_local_data_payload`（`/api/local-data`）裡呼叫結構計算。

### 4.4 前端：個股頁頂部「結構指紋卡」

- **位置**：個股詳情頁頂部摘要區（股價/漲跌/體質燈號同層），K 線圖**之前但屬於摘要**；不可做成「看完才往下」的閘門感——視覺上與體質卡並列即可。
- **DOM（index.html）**：新增 `<section id="structureCard" class="structure-card" hidden>`。
- **app.js**：`renderStructureCard(payload.structure)`：
  - 頂部：`title`＋`subtitle`＋一個常駐免責小字（`disclaimer`）。
  - 六列長條：每列 `label` + `bar_level/bar_max` 的格子（■□）+ 點擊/hover 顯示 `summary`、`forbidden`、`overlap_note`、連 glossary。
  - `synchrony` 維顯示鎖頭 + 「需市場資料（Phase 2）」。
  - **信心視覺降級**（依 `grade`）：
    - `high` → 實色。
    - `medium` → 半透明 + 標「僅供參考」。
    - `low` / `insufficient` → 灰色虛線 + 標「資料不足」，**不顯示**精確小數。
  - **顏色禁用紅綠**（避免被當漲跌方向訊號）；用中性藍/灰階。
- 若 `app.js` 太大，可放獨立 `app/ui/static/structure_card.js`，或在 `app.js` 用明確分區註解 `// ===== Structure Fingerprint Card =====`。

### 4.5 glossary（`app/glossary/terms.json`）

新增詞條（格式：`term/aliases/plain/how_to_read`），至少：`延續性`、`複雜度`、`波動聚集`、`噪音色`、`湍流程度`、`同步性`。`plain` 用白話，`how_to_read` **必須**含「這是描述、不是買賣指令」類提醒。

### 4.6 Wave S2 驗收

- `python -m pytest -q` 全綠（含新測試；既有 264 不可變紅）。
- `node --check app/ui/static/app.js`（若改了它）。
- 瀏覽器 smoke：**長歷史**（2330，六維皆 high）與**短歷史新股**（多維 grade=insufficient、灰虛線、不崩）。
- 紅線測試（§7）通過。

---

## 5. Wave S3 — 報告整合 + 快取硬化

- `app/exporters/html_report.py` 與 Excel：加「結構指紋」簡化版（六維文字 + 數值 + 充足度 + 免責），與體質卡並列。
- 確認快取命中不重算（log 或測試驗證）。
- 文件：`docs/structure-fingerprint.md`（方法、參數、限制；給進階使用者）。
- **不做**：SampEn 進卡、全市場結構排行、MFDFA、市場雷達。

---

## 6. Wave S4 —（之後，前置：跨股載入器）市場心智雷達

**本輪不做。** 先決條件：`app/analyze/cross_section.py`（對齊 ≥30 檔 returns 矩陣）。屆時才做 dispersion / 平均相關 / Kuramoto r / 雪崩冪律，放「雷達中心」新分頁，名稱可用「市場心智雷達」。

---

## 7. 紅線測試（強制，必做）

新增 `tests/test_structure_guardrails.py`：掃描 registry 文案、`build_structure_payload` 範例輸出、報告輸出，**不得**出現下列字（中英）：

```
會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|機率|崩盤|快崩|看多|看空|多單|空單|買訊|賣訊
Buy|Sell|Bullish|Bearish|Win[- ]?Rate|Target[- ]?Price
```

- 「雪崩/臨界」類字眼（本輪沒有，未來若出現）一律要帶「**非預告**」尾綴——也寫進此測試。
- 每維**必須有** `forbidden` 文字（非空）。

---

## 8. 絕對不要做（Do-NOT）

- ❌ 不要把結構指標塞進 `indicator_registry.py` / K 線副圖系統（它們是六維卡，不是疊線）。
- ❌ 不要改 `structure_metrics.py` 的演算法或函式簽名。
- ❌ 不要在 `/api/local-data` 全市場批次算結構。
- ❌ 不要用紅綠色當維度色票。
- ❌ 不要顯示「準確率/機率/勝率/目標價/買賣」任何字眼。
- ❌ 不要做 Tier D（量子/Hopfield/集體意識）——連 import 都不要。
- ❌ 不要顯示 confidence 的原始小數給使用者（要轉成 high/medium/low/不足）。

---

## 9. 最終驗收清單

```
[x] structure_registry.py 完成；bar_level / sufficiency / build_structure_payload 有測試
[x] /api stock payload 含 "structure"，且失敗時不影響個股頁其他區塊
[x] 快取以 last_close_date 為 key；local-data 未被牽連
[x] 個股頁頂部結構指紋卡：六維長條 + 信心三級降級 + hover 四要素 + 常駐免責
[x] glossary 六維詞條（how_to_read 含「非買賣指令」）
[x] 紅線測試通過；每維 forbidden 非空
[x] python -m pytest -q 全綠（既有 + 新增）
[x] python -m compileall app ；node --check app/ui/static/app.js
[x] 2330 API smoke 正常；短歷史資料在 API/單元測試正確灰掉
```

完成記錄（Codex 2026-06-24）：
- 新增 `app/analyze/structure_registry.py`，包住既有 `structure_metrics.py`，集中六維 metadata、bar level、充足度、紅線文案與 payload。
- `build_stock_payload()` 新增 `structure`，並使用 `structure::<stock_id>::<last_close_date>::250` 快取；`/api/local-data` 已用測試鎖定不可觸發結構計算。
- 個股頁新增頂部 `structureCard`，以中性藍灰長條呈現六維；資料不足降級、同步性鎖定、常駐免責與 glossary link 已接。
- HTML 研究報告與 Excel 個股匯出皆新增「結構指紋」。
- 新增 `docs/structure-fingerprint.md` 與 guardrail 測試。
- 驗證：相關測試、`node --check app/ui/static/app.js`、`python -m compileall app`、HTTP runtime smoke（`/api/stocks/2330?days=365` 回 6 維 high）已過。此環境沒有 Playwright/Chrome/Edge，所以未做截圖式瀏覽器驗證。

完成後 commit（訊息建議：`Add structure fingerprint card (registry+api+ui)`），**先不要 push**，交回給使用者檢視。

---

## 10. 給你（Codex）寫數值碼時的提示

未來若要實作 `multifractal_width()` 等數值函式，請：用純 Python（不引入 numpy/scipy，與專案一致）、明確處理排序平手（tie-break）、嚴守最小樣本門檻、並**先寫合成資料黃金測試再寫實作**。沒有黃金測試的數值函式不准合進 main。

---

*本指導書未變更程式碼、未 commit、未 push。Codex 可從 Wave S1 開始。*
