# 大型 K 線圖 + 指標庫 + 標註：施工藍圖

> ## ✅ 實作審核（2026-06-24，未改 code / 未 commit / 未 push）
>
> Codex 已建 `indicators.py(815) / indicator_registry.py(285) / patterns.py(199) / scores.py(114)`＋前端面板、預設組合、標註、圖高/座標切換（工作區未 commit）。引擎架構正確、公式大致照藍圖。**但測試員說「少了很多、篩選怪怪的」是對的，根因如下：**
>
> ### 🔴 核心根因：引擎算了 ~150 個特徵，但 UI 只畫「線型/副圖」兩種
> `app/ui/static/app.js:3472` `isChartVisualFeature` 只放行 `display_type ∈ {overlay, subplot}`。後果：
> - **`value / flag / pattern / score` 類全部不顯示**（報酬率、乖離、斜率、缺口、K棒旗標、突破、量價、型態、評分…約 80+ 個）。`patterns.py`、`scores.py` 明明有算（`indicators.py:515,519` 已併入 payload），但前端沒有任何渲染路徑 → 等於白算。
> - **整個分類在面板消失**：`renderIndicatorPanel`（`app.js:3560`）用 `byCategory.has()` 過濾，凡是沒有 overlay/subplot 的分類（基礎價格、K棒結構、缺口、報酬率、均線狀態、動能、突破、型態、評分）整組不出現 → 這就是「少了很多東西」。
> - **預設組合被默默砍**：`applyChartEnabledKeys`（`app.js:3481`）用 `chartVisualFeatureKeys()` 當白名單，按「技術派/全部」時，value/flag/score 全被濾掉、看起來沒反應 → 這就是「篩選怪怪的」。
>
> **修法（給 Codex）**：把「能不能被開關」與「畫在哪裡」分開。
> 1. 面板要列出**所有**分類與特徵（不要用 `isChartVisualFeature` 過濾面板與預設）。
> 2. 依 `display_type` 給不同渲染：`overlay`→主圖疊線、`subplot`→副圖、`value`→「目前數值」讀數表＋十字游標顯示、`flag`→狀態徽章列、`pattern`→型態卡（低信心＋免責）、`score`→評分卡（實驗室＋免責）。
> 3. `applyChartEnabledKeys` 的白名單只用來決定「主圖能疊哪些線」，不要拿來砍 value/flag/score。
>
> ### 🟠 與你原始清單相比，registry 真的還缺這些（要補登錄＋計算）
> - **整個「綜合評分」類沒做**：`trend_score / momentum_score(總) / volume_score / risk_score / breakout_score / entry_score / exit_score / overall_score`（8 個，連分類都沒有）。
> - **AI 衍生特徵只做了 5／13**，缺：`consolidation_score、breakout_probability、reversal_probability、trend_quality_score、volume_quality_score、volatility_compression_score、trend_continuation_score、primary_uptrend_score、distribution_score`。
>   （`*_probability` 對外仍以「分數」呈現＋免責，內部 key 可留。）
> - **動能缺**：`momentum_60`、`roc_60`（registry 只有 5/10/20）。
> - **EMA 斜率缺**：`ema12_slope、ema26_slope`（你清單有；registry 只有 maX_slope）。
> - 小漏：`price_to_ma10`（有 ma10 卻無對應乖離）；基礎價格的原始 `open/high/low/close` 未列為可選讀數。
>
> ### 🟡 其他要修的小問題
> - 本地資料排序 `levelRank`（`app.js:5725`）用了「正常」（後端從不產生）且缺「區間中」→ 區間中個股被當未知排序。應改成 `{接近波壓,接近波撐,區間中,資料不足}`。
> - `PRESETS["all"]` 會一次開到 pattern/score（risk 3/4）。建議「全部」仍預設**不**含實驗室層，或開啟時強制顯示一次免責。
> - 請順帶確認 Wave 1 的 **SR-1（突破/破底回 null）**、**MA-1（暖身棒、季線從可視第一根有值）** 是否已隨 `186b880` 落實（本次未逐一回歸）。
>
> ### 結論
> 引擎與資料層做得不錯，**問題集中在「呈現層只露出兩種型態」**——所以看起來像少了大半、篩選沒反應。先補渲染(value/flag/pattern/score)＋放開面板過濾，立刻會「變多」；再補上綜合評分與缺的 AI 特徵就接近你原始清單。建議排成 **Wave 2.5（呈現層補強）** 優先做。
>
> ---


- 目的：把「近一年收盤價(日線)」升級為可放大的大圖，掛上整套可開關收合的 OHLCV 指標、型態、評分/預測層，並讓使用者標註。
- 立場：本文件只做規劃，**未改 code、未 commit、未 push**。供你與 Codex 照做。
- 前提：把上輪確認的 **SR-1（支撐壓力算錯邊）**、**MA-1（圖表均線暖身不足）** 直接修進新引擎，不要蓋在舊 bug 上。

---

## 1. 核心原則（先讀這段）

1. **一個引擎、一次計算**：所有 OHLCV 衍生特徵（清單 9 成）都是對同一份日線做一次計算就能全拿。建 `app/analyze/indicators.py`，輸入 OHLCV 序列 → 輸出「整包特徵」。前端只負責「選哪些顯示」。加指標≈零成本、好測試。
2. **特徵登錄表（registry）驅動 UI**：每個特徵有 metadata：`key / 中文名 / 類別 / 顯示型態(線疊圖/副圖/旗標/數值) / 預設開關 / 風險層級(1–4) / 說明`。前端的開關面板、預設組合、名詞小教室全部讀這張表 → 不用為每個指標寫死 UI。
3. **暖身棒**：算長均線/長指標要多抓資料、只顯示可視段（解 MA-1）。
4. **四層風險分級**：第 1 層(事實型) 預設可開；第 3 層(型態) 與第 4 層(評分/預測) **預設關閉 + 免責 + 標「實驗/低信心」**。你現在有投資人，信任最值錢。
5. **分波施工**：雖然要全做，但照 Wave 1→6 出貨，每波都能跑、有測試。

---

## 2. 後端架構

### 2.1 新模組
```
app/analyze/indicators.py        # 主引擎：compute_features(prices) -> FeatureBundle
app/analyze/indicator_registry.py# 特徵登錄表(metadata) + 預設組合
app/analyze/patterns.py          # 型態辨識(第3層，低信心)
app/analyze/scores.py            # 評分/機率(第4層，實驗室，免責)
```

### 2.2 資料契約（API）
- 既有個股 payload 增加 `features` 區塊；或新端點 `GET /api/stocks/{id}/features?set=core|tech|all`。
- 兩種輸出：
  - **逐根序列**（畫線/副圖用）：`{ key: [v0, v1, ... vN] }`，與日線 index 對齊，暖身期為 `null`。
  - **最新快照**（數值卡/評分用）：`{ key: latest_value }`。
- registry 隨 payload 一起送（或獨立 `GET /api/indicators/catalog`），前端據此渲染開關面板。

### 2.3 暖身棒（解 MA-1）
- 個股圖目前只抓「今天往回 365 天」。改成：**抓 365 + 暖身(最長指標需求，建議 +250 個交易日 ≈ +400 天)** 一起算，引擎算完後**只回傳/只顯示最後 365 天**。
- 這樣 MA240/季線/HV120 從可視第一根就有值。`api.py:587` start_date 改為 `end_date - timedelta(days=365+warmup)`，並在輸出時切片。

---

## 3. 指標公式定稿（確保正確；Codex 照這個寫）

> 慣例：序列由舊到新；不足窗格回 `null`。除非註明，標準 SMA/std 用 **母體**（ddof=0，與多數看盤軟體一致）。

### 第 1 層　事實型（預設可開，最優先）

**基礎價格**
- `previous_close = close[-2]`；`price_change = close - previous_close`；`price_change_percent = price_change/previous_close*100`
- `typical_price = (high+low+close)/3`；`weighted_price(HLCC) = (high+low+2*close)/4`；`mid_price = (high+low)/2`

**K 棒結構**（皆為當根）
- `body_size=|close-open|`；`range=high-low`；`body_ratio=body_size/range`
- `upper_shadow=high-max(open,close)`；`lower_shadow=min(open,close)-low`；各 ratio = shadow/range
- `bullish=close>open`；`bearish=close<open`
- `doji = body_ratio<0.1`；`long_body=body_ratio>0.7`；`marubozu=upper_ratio<0.05 and lower_ratio<0.05 and long_body`
- `hammer=lower_ratio>=0.5 and upper_ratio<=0.15 and body在上緣`；`inverted_hammer/shooting_star/hanging_man=對稱定義`；`spinning_top=body_ratio<0.3 且上下影皆>body`
- ⚠ 單根型態主觀，標「參考」；下跌段才叫 hammer、上漲段才叫 hanging_man（需趨勢脈絡）。

**缺口**
- `gap_up = low > prev_high`；`gap_down = high < prev_low`；`gap_percent=(open-prev_close)/prev_close*100`
- `gap_fill = 之後 N 日內是否回補到 prev_close`；`gap_fill_days = 回補所用交易日`

**報酬率**　`return_Nd = (close/close[-1-N]-1)*100`（N=1,3,5,10,20,60,120,250）；`return_ytd`(今年初起)；`return_52w=return_250d`

**SMA**　`maN = mean(close[-N:])`（5,10,20,60,120,240）— 已有 `assessment.sma` 可重用
**EMA**　`k=2/(N+1)`；種子 = 前 N 根 SMA；`ema_t=close_t*k+ema_{t-1}*(1-k)`（5,12,26,50,200）
**均線斜率**　`maX_slope = (maX_t/maX_{t-5}-1)*100`（近 5 根變化%，較穩健）
**均線距離(乖離)**　`price_to_maX=(close/maX-1)*100`
**均線排列**　`bull_alignment=ma5>ma20>ma60`；`bear_alignment=ma5<ma20<ma60`
**交叉**　`golden_cross`(主：ma20 上穿 ma60；另短線 ma5×ma20)；`death_cross`=下穿。判定：前一根 short≤long 且本根 short>long。

**動能**　`momentum_N=close-close[-1-N]`；`roc_N=(close/close[-1-N]-1)*100`；`price_acceleration=roc_5 - roc_5[-1]`（動能的變化）

**波動率**
- `daily_range=high-low`；`daily_range_percent=range/prev_close*100`
- `TR=max(high-low, |high-prev_close|, |low-prev_close|)`
- `atr_N=Wilder平滑(TR,N)`（5,14,20）：種子=前N根TR均值，之後 `atr=(atr*(N-1)+TR)/N`
- `hv_N=stdev(日對數報酬, N)*sqrt(252)*100`（20,60,120）；`annualized_volatility=hv_20`（或可選窗）

**成交量**　`volume_maN=mean(volume[-N:])`(5,20,60)；`volume_ratio=volume/volume_ma20`；`volume_spike=volume_ratio>=2`；`new_volume_high/low=近N日量新高/低`
**量價關係**　四象限 `price_up_volume_up...`（今日漲跌 × 量增減）；`obv`：漲日+vol、跌日-vol、平盤不變；`volume_trend=obv_ma斜率`

**支撐壓力(rolling)**
- `high_N=max(high[-N:])`、`low_N=min(low[-N:])`（20,60,120,250）
- `distance_to_high_N=(close/high_N-1)*100`、`distance_to_low_N=(close/low_N-1)*100`
- `distance_to_52w_high/low` = N=250
> 這組是「純滾動極值」型支撐壓力，**和樞紐法(levels.py)互補**：rolling 永遠有值、不會錯邊（直接解掉投資者對 SR 的疑慮），樞紐法給「波段轉折」位。兩種都顯示、各自標清楚名稱。

**突破**　`breakout_N=close>max(high 前N根不含今日)`；`breakdown_N=close<min(low 前N根)`；`breakout_strength=(close/該前高-1)*100`

**RSI**（Wilder，已有 `assessment.rsi`）　rsi_6/12/14/24
**MACD**　`macd=ema12-ema26`；`signal=ema9(macd)`；`histogram=macd-signal`；`golden/dead_cross`=macd 與 signal 交叉
**KD**（台股隨機指標，已有 `_kd_series`）　9 日 RSV，`K=2/3 K_{-1}+1/3 RSV`，`D=2/3 D_{-1}+1/3 K`，`J=3K-2D`；金叉/死叉
**布林**　`bb_middle=ma20`；`σ=stdev(close,20)`；`bb_upper=mid+2σ`；`bb_lower=mid-2σ`；`bb_width=(upper-lower)/mid`；`bb_position=(close-lower)/(upper-lower)`；`bb_squeeze=bb_width 為近120日低檔`；`bb_breakout=close>upper or <lower`

### 第 2 層　趨勢結構（中等）
- `trend_direction`：由 ma 排列 + ma60 斜率 → 多/空/盤整
- `trend_strength`：用 **ADX(14)**（標準 DI+/DI-/DX→Wilder 平滑）
- `trend_duration`：同方向連續交易日數
- `higher_high/higher_low/lower_high/lower_low`：用修好的 `swing_pivots` 比較最近兩個樞紐

### 第 3 層　型態辨識（預設關閉、標「低信心，僅參考」）
- `double_top/bottom`、`head_and_shoulders / inverse`、`triangle/ascending/descending`、`flag/pennant`、`cup_and_handle`
- 一律以修好的 `swing_pivots` 樞紐序列做幾何規則比對，輸出 `{matched, confidence, 區間}`。
- ⚠ 自動型態辨識誤判率高；**每個都附 confidence、預設關、UI 標「實驗/參考，非訊號」**。

### 第 4 層　評分 / 預測（實驗室區、預設關閉、強免責）
- 把第 1–2 層特徵**透明加權**成 0–100 分；**不是真機率、不預測未來**。
- 例：`momentum_score=各ROC的百分位混合`；`breakout_setup_score=bb_squeeze+量縮+貼近high_20`；`mean_reversion_score=|乖離|+RSI極值`；`institutional_accumulation_score=OBV斜率+量價`；`crash_risk_score=負乖離+破線+量增下跌`。
- `*_probability` 類：**UI 一律顯示為「分數」並加註「非機率、不預測」**（或把 key 對外標籤改名，內部 key 可留）。
- 文案沿用回測模組自律：「描述目前型態的強弱分數，不代表後續走勢」。整區一個大免責 + 每張卡小字。

---

## 4. 前端設計

### 4.1 大圖 / 放大（投資者主要訴求）
- 「全螢幕」按鈕：圖表進 fullscreen modal（或 `Fullscreen API`），關閉復原。
- 可調高度：拖曳把手或「標準/高/超高」三段；記住偏好（localStorage 之外用後端 `indicator_prefs`，因 artifact 限制請用後端表）。
- 維持既有滾輪縮放/拖曳平移/框選區間。
- 加 **對數座標切換**、**% 變化座標**。

### 4.2 指標開關面板（開關收合）
- 依 registry 類別分組（基礎/K棒/缺口/報酬/均線/EMA/動能/波動/量/量價/支撐壓力/突破/RSI/MACD/KD/布林/趨勢/型態/評分）。
- 每組可收合；每個指標一個開關；hover 顯示說明（接名詞小教室）。
- **預設組合**：`新手`(MA20/MA60+量+RSI)、`技術派`(全第1層)、`全部`(含實驗室)、`自訂`。一鍵套用。
- 開關狀態存後端（見 4.4），跨裝置一致。

### 4.3 版面（多窗格）
- 主圖：K 線 + 疊圖型指標（MA/EMA/布林/rolling 高低/樞紐 SR/標註）。
- 副圖（可各自開關收合）：成交量、RSI、MACD、KD、ATR/HV、OBV。
- 十字游標：顯示「該根 OHLCV + 目前開啟的所有指標數值」。

### 4.4 標註（筆記 + 畫線，皆要）
- **筆記**：在某日期/某價位加文字，圖上顯示小圖釘，點開可看/編輯/刪。
- **畫線**：水平線（關卡）、趨勢線（兩點）、箭頭、文字框；可拖移/刪除。
- 儲存於後端 sqlite（見 §5），以 stock_id 綁定，跨裝置保留。
- 匯出報告（Excel/HTML）時可一併帶上使用者筆記。

---

## 5. 資料模型（新增 sqlite 表）
```sql
CREATE TABLE IF NOT EXISTS chart_annotations (
  id INTEGER PRIMARY KEY, stock_id TEXT NOT NULL,
  kind TEXT NOT NULL,           -- note / hline / trendline / arrow / textbox
  anchor_date TEXT, anchor_price REAL,
  anchor_date2 TEXT, anchor_price2 REAL,   -- 趨勢線/箭頭第二點
  text TEXT, color TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS indicator_prefs (
  profile_key TEXT PRIMARY KEY,  -- e.g. 'default' 或未來多使用者
  payload TEXT NOT NULL,         -- JSON: 開啟的指標、預設組合、圖高、座標
  updated_at TEXT NOT NULL
);
```
- API：`GET/POST/PATCH/DELETE /api/stocks/{id}/annotations`、`GET/PUT /api/indicator-prefs`。

---

## 6. 信任護欄（第 3、4 層必做）
- 型態與評分**預設關閉**，需使用者主動開。
- 開啟時顯示一次性說明：「這是實驗性技術型態/分數，非投資建議、不預測股價」。
- 評分卡與型態卡都帶小字免責；用「歷史/目前型態描述」措辭，避免「會漲/勝率/機率」。
- `*_probability` 對外顯示為「分數」。
- 資料不足或暖身不夠時，指標標「資料不足」而非給錯值（接既有覆蓋率/健康徽章）。

---

## 7. 分波施工順序（每波可獨立出貨 + 驗收）

**Wave 1　地基（含修 bug）**
- 建 `indicators.py` 引擎骨架 + registry + API 契約 + 暖身棒切片（解 MA-1）。
- 修 `levels.py` SR-1（突破/破底回 `null` + 標新高/新低）。
- 第 1 層「基礎價格/K棒/報酬/SMA/EMA/距離/排列」。
- 驗收：golden test 對照手算；MA60 從可視第一根有值。

**Wave 2　大圖 + 開關面板**
- 全螢幕/可調高度/對數座標；registry 驅動的分類開關 + 預設組合；十字游標數值；偏好存後端。
- 驗收：開關即時生效、偏好重整後保留。

**Wave 3　動能/波動/量/量價/突破/rolling 支撐壓力**
- 第 1 層其餘 + 副圖（量/ATR/HV/OBV）。
- 驗收：ATR/HV/OBV golden test；rolling 高低永不錯邊。

**Wave 4　震盪指標副圖**
- RSI(多週期)/MACD/KD/布林，含金叉死叉/squeeze 旗標。
- 驗收：對照看盤軟體數值（容許小數誤差）。

**Wave 5　標註（筆記 + 畫線）**
- annotations 表 + API + 圖上互動 + 匯出帶筆記。
- 驗收：增改刪、跨裝置保留、匯出含筆記。

**Wave 6　趨勢結構 + 型態辨識 + 評分/預測（實驗室）**
- 第 2 層 + `patterns.py` + `scores.py`，全部預設關 + 免責。
- 驗收：型態/評分都有 confidence/免責；預設關閉；可開關。

---

## 8. 測試計畫
- **golden tests**：每個公式準備 1–2 組手算對照（特別是 EMA 種子、ATR/RSI Wilder、布林 σ、OBV、KD 種子）。
- **邊界**：資料不足、含 None、停牌缺口、暖身不足 → 回 `null` 不報錯。
- **回歸**：SR-1 突破情境（收盤 > 所有前高）必須 `resistance=null`；MA-1 視窗第一根 MA60 必須有值。
- **效能**：引擎一次算完（單檔 ≤ 數十 ms）；大圖開很多指標仍順。
- 高風險層（型態/評分）：至少快照測「預設關閉」「帶免責欄位」。

---

## 9. 風險與注意
- **型態辨識/評分是信任最脆弱處**：誤判會讓投資人對整個產品打折。務必預設關、免責、低信心標示。
- **不要在舊 SR/MA bug 上疊功能**：Wave 1 先把 SR-1/MA-1 修進引擎。
- **效能**：第 4 層評分依賴第 1–2 層，務必同一次計算共用中間結果，別重算。
- **與既有重複**：`assessment.py` 已有 sma/rsi/kd/乖離、`historical_frequency.py` 已有 sma/rsi/kd 序列 → 引擎應成為**單一真相**，舊處改為呼叫引擎，避免三套實作再次分歧（這正是股利那輪的教訓）。

---

*本藍圖未變更任何程式碼、未 commit、未 push。確認後可由 Codex 依 Wave 1→6 實作，或指定某一波我先做。*
