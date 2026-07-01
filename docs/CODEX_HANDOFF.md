# 股票翻譯機 — Codex 自主作業手冊

> 給接手的 AI（Codex）：這份是你的作業說明書。請**邊做邊驗證**，每完成一個小步驟就跑一次驗證指令（見 §3），全綠再往下。**動工前務必先讀完 §1 紅線與 §5 工作守則**——這個專案的靈魂就是「翻譯資料、不報明牌」，違反紅線的程式碼一律不要寫。

---

## 0. 這份文件怎麼用

- 從 §6 的六大主題挑任務，**一次做一小塊**，做完立刻跑 §3 的驗證。
- 任務有 `- [ ]` 勾選框，做完改成 `- [x]` 並在該處補一行「怎麼驗的」。
- 不確定範圍的，先做**最小可行版本 + 純函數 + 測試**，不要一次大改前端或引入大型框架。
- 找不到答案時，寧可保守、可解釋，也不要臆測或加「會漲/會跌」這種結論。

---

## 1. 專案定位與紅線（最重要）

**定位**：一台「台股資料翻譯機」。把證交所(TWSE)公開資料，翻成新手看得懂的白話，同時給老手足夠的數據與技術面整理。**它不是明牌機、不是下單軟體。**

**絕對紅線（違反就是 bug）**：
1. **不預測股價、不報明牌、不給買賣建議、不下單。**
2. UI／分析層輸出**不得出現**：`便宜價`、`合理價`、`昂貴價`、`低估`、`高估`、`該買`、`該賣`、`會漲`、`會跌`、`建議買進/賣出`。
   - 估值一律用「情境／敏感度／參考／目前倍數／歷史區間／位階」這類中性詞。
   - 技術面用「偏多解讀／偏空解讀／中性」「接近波撐／波壓」並**一律附免責**（「傳統解讀，不是預測，也不是買賣建議」）。
3. **顏色規則**：紅／綠**只用於漲跌事實**（K 線紅漲綠跌）。其他面向（籌碼、體質燈號、支撐壓力）用**藍 `#1C3D5A` / 琥珀 `#B0820B` / 灰**，不可用紅綠暗示買賣。
4. **不接 LLM 做分析**：分類、解讀、總評全部是**規則式 + 常數字典**，純函數、可單元測試、固定輸入→固定輸出。
5. **隱私**：持倉等個人資料只留本地、不上傳。
6. **唯一例外**：雷達中心匯出的 Excel「傳統估價表」分頁（同事/老手版）允許出現便宜價/合理價/昂貴價——這是**刻意保留的單一例外**，其餘任何地方都不行。

> 紅線字掃描（UI 與分析層應為空；`docs/` 與本檔不算）：
> ```bash
> grep -rnE "便宜價|合理價|昂貴價|低估|高估|該買|該賣|會漲|會跌" app/ui app/analyze app/chips app/news app/explain
> ```

---

## 2. 架構地圖

Python 3.10 模組化單體 + 原生 JS 前端（無打包工具）。

```
app/
  web/server.py        # http.server 路由（GET/POST API、靜態檔）
  web/api.py           # payload 組裝：build_stock_payload / build_value_screener_payload /
                       #   enrich_screener_with_levels / build_local_data_payload / 產業代碼表
  store/sqlite_store.py# SQLite：daily_prices / dividend_records / financial_statements /
                       #   monthly_revenues / market_valuations / institutional_trades /
                       #   portfolio_transactions / watchlist / sync_runs / stock_profiles
  sync/twse.py         # TwseClient：TWSE 抓取（日線/股利/財報/營收/估值/T86法人/盤中報價）
                       #   + 批次 fetch_all_*（給全市場下載用）
  sync/service.py      # StockSyncService.sync_stock_history / sync_institutional（單檔）
  sync/bulk.py         # BulkDownloadManager（背景任務：暫停/停止/續傳/連續失敗自動暫停）
  sync/bulk_runner.py  # build_bulk_plan（prelude 抓全市場共用檔一次 + 逐檔日線 + 跳已存）
  analyze/assessment.py# 體質總評多因子（RSI=Wilder、KD 9,3,3、乖離、量能、均線、位階…）
  analyze/levels.py    # 波撐/波壓 swing-pivot + 接近偵測
  analyze/valuation_bands.py # PE/PB 歷史河流圖
  analyze/{methods,suitability,summary,valuation,vital_signs,financial}.py
  chips/institutional.py # 三大法人分析（連續賣超、可能的解讀…）
  news/classifier.py   # 規則式 利多/利空/中性 + 事件關鍵字（可調設定檔 keywords.json）
  news/risk_matrix.py  # 地雷風險矩陣（10 維、加權字典）
  news/service.py      # RSS 抓取 + payload
  explain/rule_based.py# 白話健檢報告
  catalog/stocks.py    # 股票清單（data/stock_catalog.json）
  portfolio/           # 持倉計算、XIRR、績效
  exporters/excel.py   # Excel 匯出
  glossary/            # 名詞解釋
  ui/static/index.html # 單頁三層結構（30秒看懂 / 體質估值 / 完整資料）+ 雷達中心 + 本地資料分頁
  ui/static/app.js     # 單一檔（~3800 行）。所有前端邏輯都在這
  ui/static/app.css    # 設計權杖在最上面 :root（--brand/--ink/--line/--warn/--alert/--radius…）
tests/                 # python -m unittest discover；目前 ~142 個測試
data/                  # 本地 SQLite、stock_catalog.json、value_screener.json(快取，gitignore)
run_app.bat            # 啟動本機 UI
```

**前端關鍵函式（app.js）**：`drawChart`（蠟燭+均線+量+支撐壓力+事件，滾輪縮放/拖曳）、`renderAssessment/renderAssessmentMerged`（體質總評）、`renderChipsCard`、`renderRiskRadar`、`openIndicatorGuide`+`INDICATOR_GUIDES`（教學庫）、`renderLevelsRadar`/`renderLocalDataTable`、`bulk*`（全市場下載控制）、`showSheet`（分頁切換）。

---

## 3. 怎麼跑、怎麼驗證（每改必驗）

```bash
# 1) Python 單元測試——全綠才算過
python -m unittest discover -s tests

# 2) 前端語法檢查（app.js 是單一大檔，語法錯會整頁掛掉）
node --check app/ui/static/app.js

# 3) 全專案編譯掃描
python -m compileall app tests

# 4) 紅線字掃描（見 §1）
grep -rnE "便宜價|合理價|昂貴價|低估|高估|該買|該賣|會漲|會跌" app/ui app/analyze app/chips app/news app/explain

# 5) 啟動實機看
#   Windows: run_app.bat ；或： python -m app.cli serve  （視專案入口而定）
```

**前端「執行期」驗證（重要，`node --check` 只驗語法、抓不到 runtime 錯）**：寫一個 DOM-stub harness，把 `app.js` 在 Node 內 eval、用假的 `document/window/fetch`，再呼叫剛改到的 render 函式餵假資料，確認不丟錯。骨架：

```js
const fs=require("fs"); let code=fs.readFileSync("app/ui/static/app.js","utf8");
const ctx=new Proxy({},{get:(t,p)=>p==="measureText"?()=>({width:10}):()=>undefined,set:()=>true});
const el=()=>new Proxy({style:{},classList:{add(){},remove(){},toggle(){},contains:()=>false},dataset:{}},
  {get:(t,p)=>p in t?t[p]:(p==="getContext"?()=>ctx:(p==="getBoundingClientRect"?()=>({left:0,top:0,width:960,height:440}):el())),set:()=>true});
global.document={querySelector:()=>el(),getElementById:()=>el(),querySelectorAll:()=>[],createElement:()=>el(),addEventListener(){},body:el(),documentElement:el()};
global.window={devicePixelRatio:1,addEventListener(){},matchMedia:()=>({matches:false}),setInterval:()=>1,clearInterval(){},setTimeout:()=>1,location:{}};
global.navigator={userAgent:""}; global.fetch=()=>Promise.resolve({ok:true,json:()=>Promise.resolve({})});
code += `;/* 在這裡呼叫你改到的函式餵假資料，例如 renderAssessment({...}); drawChart(); */ console.log("OK");`;
try{ eval(code); }catch(e){ console.log("THROW:", e.message); }
```

**驗收門檻**：上面 1–4 全過、harness 印出 OK、紅線掃描為空，且**新功能要有對應單元測試**。

---

## 4. 目前已完成（不要重做）

- K 線：紅漲綠跌蠟燭、MA5/20/60、成交量、**滾輪縮放 + 拖曳平移**、事件標記（財報/營收/除息/風險新聞）、統一 tooltip。
- **支撐/壓力**：swing-pivot（取最接近現價的上方壓力/下方支撐），短(20)/波(60)/長(240) 三週期可圖例開關。
- **體質總評**：多因子（均線/乖離/RSI(Wilder)/KD/量能/位階/籌碼/估值/基本面/消息）→ 體質等級 + 30 秒結論 + 決定前清單；每因子有「📖 怎麼看」教學彈窗。
- **三大法人**：T86 抓取、近 20 日趨勢、連續賣超、可能的解讀；獨立「讀取三大法人」按鈕。
- **地雷雷達**：新聞風險矩陣。**新聞**：規則式利多/利空/中性 + 事件標籤 + 溫度計。
- **估值**：PE/PB 河流圖、股利情境（自適應適用性）。
- **雷達中心**：全市場股利情境/高殖利率/陷阱、漲跌榜、**波段關卡提醒卡**、**全市場一鍵下載**（背景+保護）。
- **本地資料分頁**：盤點每檔日線筆數/最後資料日(過期警示)/法人/波段關卡。
- 持倉（半自動新增交易、XIRR、對 0050）、Excel 匯出、名詞解釋彈窗。
- 指標通過驗證：RSI 用 **Wilder 平滑**（非簡單平均）、KD 9,3,3 標準、SMA、KD 皆有測試。

---

## 5. 工作守則

1. **小步快驗**：一次一個小改動 → 跑 §3 → 綠了再下一步。不要一次大重構。
2. **純函數優先**：分析/計算邏輯放 `app/analyze` 或對應模組，寫成純函數並**補單元測試**到 `tests/`。
3. **前端是單一 `app.js`**：維持它語法有效（`node --check`），改完用 harness 跑一次。新樣式用 `app.css` 既有設計權杖（`:root` 變數），不要硬寫色碼破壞一致性。
4. **守紅線**（§1）。任何「結論」都要可解釋 + 附免責，且不可越線成買賣建議。
5. **資料來源誠實**：數字旁標資料日期；過期要醒目。抓不到網路要優雅降級，不可假裝成功。
6. **效能**：全市場相關運算只讀本地 DB；別在 request 內逐檔重抓 TWSE 全市場檔（會被擋）。
7. 改完更新本檔對應任務的勾選與「怎麼驗的」。

---

## 6. 任務（六大主題）

### 6.1 延伸功能 ＋ UI 架構優化／更好的排版

**目標**：頁面是逐步長出來的，視覺語言已統一一輪（卡片標題強調條＋分隔線、章節分隔帶）。接著把「常看的」做成重點、次要的收合，並補互動細節。

- [x] **本地資料分頁**加排序與篩選：可依「日線筆數／最後資料日／波段關卡」排序；快速篩「只看過期」「只看接近波壓」「只看接近波撐」。
  - 2026-06-22 進度：新增 `app/analyze/local_data.py` 的純函數 `filter_sort_local_data_items()`；API payload 預設排序；前端本地資料分頁新增排序下拉與快速篩選，並用同口徑 JS 函式處理畫面資料。
  - 怎麼驗：`python -m unittest tests.test_local_data`、JS DOM-stub harness、瀏覽器實點「只看過期」+ 切排序下拉，確認 8 / 38 檔與 active 狀態；`python -m unittest discover -s tests`（159 tests）、`node --check app/ui/static/app.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
  - 視覺驗證：用本機 `http://127.0.0.1:8765/` 拍桌面與手機寬度截圖；手機版先發現 sidebar 擠爆主內容，已補 RWD 外框規則後重拍，確認 body 無水平溢出、資料表改在表格容器內水平捲動。
  - 2026-06-22 補充：波段關卡提醒卡新增「更新資料」按鈕，可一次批次同步目前提醒清單內多檔目標；新增本機端點 `/api/sync/batch`，會去重、最多 20 檔、逐檔回報成功/失敗，public ASGI 仍維持唯讀不開放同步。
  - 怎麼驗：新增 `app/web/sync_batch.py` 與 `tests/test_sync_batch.py`；DOM-stub harness 呼叫 `renderLevelsRadar()` / `syncLevelsTargets()`，確認送出 `stock_ids=["2330","2408"]`；headless Chrome/CDP 拍手機暗色模式截圖 `C:\Users\a0976\AppData\Local\Temp\stock-levels-sync-button-mobile-fixed.png`，DOM 量測 `bodyOverflowX=false`、按鈕可用、16 檔目標；完整 `python -m unittest discover -s tests`（171 tests）、`node --check app/ui/static/app.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
  - 2026-06-22 修正：若瀏覽器仍看不到新按鈕，是 PWA service worker 先回舊 shell cache。已把 `sw.js` 升到 `stock-translator-shell-v2`，app shell 改 network-first，替換舊 shell cache 時自動 reload controlled clients；前端也補 `/api/sync/batch` 不存在時退回既有 `/api/sync` 逐檔同步，降低舊 server 行程的相容風險。
  - 怎麼驗：`python -m unittest tests.test_pwa_assets tests.test_sync_batch`、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、fallback DOM-stub harness 印出 `OK levels fallback harness`；完整 `python -m unittest discover -s tests`（171 tests）、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`；headless Chrome/CDP 重拍 `C:\Users\a0976\AppData\Local\Temp\stock-levels-sync-button-after-sw-fix.png`，確認按鈕文字「更新資料」、可按、16 檔目標、`bodyOverflowX=false`。
  - 2026-06-22 補充：波段關卡提醒每列新增個別「更新」按鈕，與「看個股」並列；按單檔只同步該股票並刷新波段提醒卡，不強制跳頁。列本身不再作為波段提醒的點擊目標，避免誤觸。
  - 怎麼驗：`python -m unittest tests.test_sync_batch`、單檔 DOM-stub harness 印出 `OK single level sync harness` 並確認只送 `stock_ids=["2408"]`；headless Chrome/CDP 拍 `C:\Users\a0976\AppData\Local\Temp\stock-levels-individual-update-desktop.png`，DOM 量測 `individualButtons=15`、`bodyOverflowX=false`，人工檢查每列右側「更新 / 看個股」不擠壓；完整 `python -m unittest discover -s tests`（171 tests）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
  - 2026-06-22 補充：整批「更新資料」改成 2 檔並行工作佇列，每完成一檔就補下一檔；避免逐檔等待太慢，也避免一次丟太多請求造成 TWSE 或 SQLite 壓力。
  - 怎麼驗：平行 DOM-stub harness 印出 `OK parallel level sync harness {"syncCalls":4,"maxActiveSyncRequests":2}`，確認最大同時 `/api/sync` 為 2；headless Chrome/CDP 拍 `C:\Users\a0976\AppData\Local\Temp\stock-levels-parallel-status.png`，確認狀態文字 `更新中 0/15・同時 2 檔`、單列高亮且 `bodyOverflowX=false`；完整 `python -m unittest discover -s tests`（171 tests）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
- [x] **重點卡聚焦**：個股頁把體質總評 / K 線 / 法人三張做成主視覺（較大），其餘（健檢六卡、估值細項）預設收合可展開。
  - 2026-06-22 進度：新增 `#stockFocus` 重點卡區，頁面載入時把現有體質總評、K 線、法人籌碼三張卡搬入主工作區；K 線桌面加大，健檢六卡與估值情境改成預設收合的 `<details>`，保留原 ID 與資料渲染流程。
  - 怎麼驗：瀏覽器開 2330，確認三張卡父層都是 `stockFocus`、健檢與估值預設 `open=false`；實點展開健檢/估值後分別看到 6 張健檢卡與 3 張估值卡；桌面與手機寬度截圖確認 header / 重點卡不破版；完整驗證 `python -m unittest discover -s tests`（159 tests）、`node --check app/ui/static/app.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
- [x] **狀態一致化**：所有卡片的「載入中 / 無資料 / 抓取失敗」用同一套樣式與文案。
  - 2026-06-22 進度：新增 `.state-message` 共用狀態元件與 `stateMessageHTML()`；已套用在自選股空狀態、dashboard 空清單、雷達中心空清單、波段關卡空狀態、體質總評空狀態、法人籌碼空狀態、本地資料篩選空結果。錯誤/警示仍用中性與 alert 系色，不用紅綠暗示買賣。
  - 怎麼驗：`node --check app/ui/static/app.js`、相關單測、完整 `python -m unittest discover -s tests`（159 tests）、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`；另用 headless Chrome 開本機 app、點 2330、捲到法人卡截圖，確認空狀態樣式可見且 `bodyOverflowX=false`。
- [x] **RWD**：窄螢幕（手機寬度）下三層與卡片不破版（為 §6.3 鋪路）。
  - 2026-06-22 進度：補 app shell / topbar / rail / workspace / 本地資料表在 760px 以下的基礎 RWD；個股頁手機 header 改 grid，常見 grid（報價、健檢、指標、估值、營收/財報）加手機單欄/雙欄規則。
  - 怎麼驗：資料頁先用 in-app browser 拍手機圖抓到 sidebar 擠爆主內容，修後重拍確認 body 無水平溢出；個股頁用 headless Chrome 390px 開 2330，拍 top 圖確認 header/focus 入口不破版；再打開健檢與估值 details，DOM 量測 `reportOpen=true`、`valuationOpen=true`、`bodyOverflowX=false`、`overflow=[]`。
- [x] （可選）深色模式：用 `:root` 變數做 `[data-theme="dark"]` 覆寫。
  - 2026-06-22 進度：新增 topbar 主題切換鈕、早期 theme bootstrap、`localStorage` 偏好記憶與 theme-color 同步；CSS 新增 `:root[data-theme="dark"]` 變數覆寫，並把表面、輸入框、狀態色、K 線/估值 canvas 背景接到主題變數。
  - 怎麼驗：新增 `tests/test_ui_theme.py`；`python -m unittest tests.test_ui_theme`、theme DOM-stub harness（`applyTheme("dark")` / `toggleTheme()`）印出 `OK theme harness`；完整 `python -m unittest discover -s tests`（168 tests）、`node --check app/ui/static/app.js`、`python -m compileall app tests`、源碼紅線掃描 `NO_MATCHES`。
  - 視覺驗證：用 headless Chrome/CDP 強制 dark preference 開 2330 個股頁，拍桌機與手機截圖 `C:\Users\a0976\AppData\Local\Temp\stock-theme-dark-desktop.png`、`C:\Users\a0976\AppData\Local\Temp\stock-theme-dark-mobile.png` 並人工檢查；DOM 量測桌機/手機皆 `theme=dark`、`bodyOverflowX=false`、`focusCards=3`、K 線 canvas 背景 `rgb(15, 24, 34)`。
- **驗收**：node --check + harness 過；視覺一致；無紅線字；新增的排序/篩選有純函數 + 測試。

### 6.2 網頁化的可能性（研究 + 最小落地）

**目標**：它目前已是「本機網頁 App」（`http.server` + 靜態檔）。要評估「對外網頁化」的路與風險。**先產出評估文件 `docs/web-deploy-評估.md`，再做最小落地**。

- [x] 盤點現況限制：`http.server` 是單執行緒、無認證、TWSE 速率、本地 SQLite、個人持倉（**隱私紅線**：對外多人就不能把持倉混在一起）。
- [x] 評估方案：(a) 換成正式框架（FastAPI/Flask）+ ASGI/WSGI；(b) 唯讀公開資料站（只開放查股/雷達，不含個人持倉）；(c) 自架單人用。
- [x] 列出必備工程：多使用者/分離個人資料、TWSE 抓取改背景快取層（不要每請求打）、靜態資源 cache、錯誤頁、基本資安。
  - 2026-06-22 進度：完成 `docs/web-deploy-評估.md`，結論是保留本機版、另開公開唯讀 ASGI 版；公開版不得開持倉、交易、自選寫入、同步/全市場下載等端點。
- [x] 最小落地：把 `value_screener` / 個股查詢這類**唯讀**端點，包成一個能 `uvicorn`/`gunicorn` 跑的版本（持倉維持本地、預設關閉）。
  - 2026-06-22 進度：新增 `app/web/public_asgi.py`，提供 `app.web.public_asgi:app` 給 `uvicorn`；公開版 GET 只開靜態檔、glossary、search、stock、quote、value-screener、local-data/local-stocks、daily-price、news；`/api/portfolio` 與 `/api/watchlist` 回空資料，`/api/stocks/{id}` 強制 `is_watchlisted=false`，POST/PUT/DELETE 回 405。
  - 怎麼驗：新增 `tests/test_public_asgi.py` 鎖住「不洩漏本地持倉/自選」「拒絕寫入」「唯讀 stock/search 可用」；`python -m unittest discover -s tests`（162 tests）全綠；uvicorn smoke：`/` 回 200、`/api/portfolio` positions/transactions 皆 0、`/api/stocks/2330` 可讀且 `is_watchlisted=false`、POST `/api/watchlist` 回 405。
- **驗收**：評估文件完成；最小落地版能本機以正式 server 跑起來且測試全綠；個人持倉預設不對外。

### 6.3 APP 化的可能性（Android）

**目標**：盡量重用現有網頁前端。**先產出 `docs/android-評估.md`**。

- [x] 比較方案：**PWA**（可安裝、離線殼）／**WebView 殼**（Capacitor / TWA / Kotlin WebView 指向本機或遠端後端）／原生（成本高，不建議）。
- [x] 點出後端難點：後端是 Python，Android 上不易直接跑 server → 要嘛**後端遠端化**（接 §6.2），要嘛 Chaquopy/BeeWare（重）。給出建議路線（多半是 PWA 或 WebView+遠端後端）。
  - 2026-06-22 進度：完成 `docs/android-評估.md`，建議先 PWA，再視需求用 WebView/TWA/Capacitor 包殼；後端走 §6.2 public ASGI 或自架，不建議直接在 Android 跑 Python server。
- [x] 最小落地：把前端做成 **PWA**（manifest + service worker，先做「可安裝 + 靜態快取」，資料仍走 API）。RWD（§6.1）是前提。
  - 2026-06-22 進度：新增 `manifest.webmanifest`、`sw.js`、`app-icon-192.png`、`app-icon-512.png`；`index.html` 掛 manifest/theme-color/icon；`app.js` 註冊 `/sw.js`；本機 server 與 public ASGI 都新增 `/manifest.webmanifest`、`/sw.js` 根路由。service worker 只 cache app shell，`/api/` 明確走 network。
  - 怎麼驗：新增 `tests/test_pwa_assets.py` 檢查 manifest/installable basics、icon 尺寸、SW 不 cache API、HTML/JS registration；本機 server 8767 smoke：manifest standalone、SW 200 且含 API bypass；public ASGI 8768 smoke：manifest scope `/`、SW 200；`python -m unittest discover -s tests`（165 tests）、`python -m compileall app tests`、`node --check app/ui/static/app.js`、源碼紅線掃描 `NO_MATCHES`。
  - 2026-06-22 補驗：`npx --yes lighthouse --version` 為 13.4.0；新版 Lighthouse 已移除 `pwa` category，`--only-categories=pwa` 會回 `unrecognized category`。改跑完整 Lighthouse JSON 報告 `C:\Users\a0976\AppData\Local\Temp\stock-lighthouse-report.json`，分類分數：performance 0.71、accessibility 0.96、best-practices 1、seo 0.91、agentic-browsing 0.99；可見 viewport 相關 audit 通過。PWA 可安裝基本項以 manifest/SW/route tests 與 smoke 驗證為準。
- **驗收**：評估文件完成；PWA manifest/SW 加好，manifest/SW/route tests 與 Lighthouse 13 可用分類已補驗；桌面版不受影響（測試全綠）。

### 6.4 K 線圖：時段選取與計算

**目標**：讓使用者在 K 線上**框選一段時間**，即時算出該區間統計。**純計算寫成可測函式**。

- [x] 後端/前端純函數 `computeRangeStats(prices, startIdx, endIdx)`：回傳 期間漲跌幅、起訖價、區間最高/最低、振幅%、區間均量、交易日數、(可選)年化波動度（日報酬標準差×√252）、區間 VWAP。**全是事實統計，不得有買賣結論。**
  - 2026-06-22 進度：新增 `app/analyze/range_stats.py` 的 `compute_range_stats()` / `computeRangeStats`，前端新增同口徑 `computeRangeStats()`；統計包含區間漲跌、起訖收盤、最高/最低、振幅、均量、交易日數、年化波動度、VWAP。
  - 怎麼驗：`python -m unittest tests.test_range_stats`、`python -m unittest discover -s tests` 全綠（154 tests）。
- [x] K 線互動：拖曳框選一段（或點兩個端點）→ 在圖上反白區間 + 跳出小面板顯示上面統計；可清除。
  - 2026-06-22 進度：K 線圖新增「框選區間」與「清除區間」按鈕；框選時圖上反白，圖下方顯示區間統計面板。
  - 怎麼驗：DOM-stub harness 呼叫 `setupChart()`、`toggleChartRangeMode()`、`handleChartMouseDown()`、`handleChartPointerMove()`、`handleChartMouseUp()`、`renderRangeStatsPanel()`、`clearChartRange()`，印出 `OK`。
- [x] 與既有縮放/拖曳不衝突（例如按住 Shift 拖曳＝框選，一般拖曳＝平移；或加一顆「框選」模式鈕）。
  - 2026-06-22 進度：一般拖曳仍走平移；框選模式或 Shift 拖曳才進區間選取；滾輪縮放流程未改。
  - 怎麼驗：`node --check app/ui/static/app.js`、DOM-stub harness 印出 `OK`。
- [x] 教學：給「📖 怎麼看區間統計」一則（振幅/波動度白話解釋）。
  - 2026-06-22 進度：`INDICATOR_GUIDES.range` 已補期間漲跌幅、振幅、年化波動度、VWAP 的白話說明與免責。
  - 怎麼驗：`node --check app/ui/static/app.js`、紅線掃描回 `NO_MATCHES`。
- **驗收**：`computeRangeStats` 有單元測試（含已知數列驗算）；harness 跑框選流程不丟錯；面板數字正確；無紅線字。
  - 2026-06-22 驗收：`python -m unittest discover -s tests`、`node --check app/ui/static/app.js`、`python -m compileall app tests`、紅線掃描、DOM-stub harness 均通過。

### 6.5 增設更多股票小白導引知識

**目標**：強化「翻譯機 + 教學」定位。沿用既有 `INDICATOR_GUIDES`（app.js）與名詞解釋彈窗（glossary）。

- [x] 擴充名詞庫：本益比、每股淨值、殖利率、除權息（填息/貼息）、融資融券、借券賣出、ETF、停損/停利、複利、分散風險、流動性、市值… 每則：白話定義 + 怎麼看 + 提醒（非建議）。
  - 2026-06-22 進度：新增每股淨值、填息/貼息、融資融券、借券賣出、ETF、停損/停利、複利、分散風險、流動性、市值、振幅、年化波動度、VWAP、支撐/壓力等名詞；glossary payload 新增 `reminder`。
  - 怎麼驗：`python -m unittest tests.test_glossary`、`python -m unittest discover -s tests` 全綠（156 tests）。
- [x] 新手導覽：第一次進個股頁時，用 coachmark 或一張「新手須知」卡帶看各區塊（可關、可重看）。
  - 2026-06-22 進度：個股頁新增「新手須知」卡，第一次進個股頁自動顯示，收起後記到 localStorage，導覽列可重看。
  - 怎麼驗：DOM-stub harness 呼叫 `showNewbieGuide()`、`hideNewbieGuide()`、`maybeShowNewbieGuide()` 印出 `OK`；`node --check app/ui/static/app.js` 通過。
- [x] 「30 秒看懂」再強化：把目前資訊濃縮成更白話的一段，連到各教學。
  - 2026-06-22 進度：公司簡述會顯示 `beginner_sentence`，並用 `renderGlossaryText()` 把摘要中的名詞連到 glossary 彈窗；第一個 `watch_items` 也顯示在提醒列。
  - 怎麼驗：`python -m unittest tests.test_web_api`、DOM-stub harness 呼叫 `renderCompanyBrief()` 與 `showGlossary()` 印出 `OK`。
- [x] 把 §6.4 的振幅/波動度、§4 的支撐壓力都納入教學。
  - 2026-06-22 進度：`INDICATOR_GUIDES.range` 補振幅、年化波動度、VWAP；名詞庫補振幅、年化波動度、VWAP、支撐/壓力；原支撐壓力教學保留。
  - 怎麼驗：`node --check app/ui/static/app.js`、`python -m unittest tests.test_glossary`、紅線掃描回 `NO_MATCHES`。
- **驗收**：每則教學都有免責、無紅線字；glossary/guide 開啟 harness 不丟錯；內容用字適合完全新手。
  - 2026-06-22 驗收：`python -m unittest discover -s tests`、`node --check app/ui/static/app.js`、`python -m compileall app tests`、紅線掃描、DOM-stub harness 均通過。

### 6.6 更多「Keywords」（規則式字典擴充）

**目標**：分類/解讀更準。全部是**可調設定檔 + 常數字典**，不接 LLM。

- [x] 新聞分類 `app/news`：擴充 `keywords.json`（利多/利空加權字）、`classifier.py` 的事件關鍵字、`risk_matrix.py` 的風險詞（地雷字）。注意去重（已有 `_dedupe_overlaps`）。
  - 2026-06-22 進度：已補供應鏈長約/交付、財報內控、資安事件、訂單延遲/取消、存貨跌價等第一批規則字；新聞 payload 的系統產生理由已走 `sanitize_summary()`，避免理由文字吐出禁止字眼。
  - 怎麼驗：`python -m unittest tests.test_news_classifier tests.test_news_risk_matrix`、`python -m unittest discover -s tests`、`node --check app/ui/static/app.js`、`python -m compileall app tests`、DOM-stub harness 印出 `OK`、紅線掃描回 `NO_MATCHES`。
- [x] 白話解釋 `app/explain/rule_based.py`：增加更多情境字眼→白話句子的對應，讓健檢報告更口語、更多元。
  - 2026-06-22 進度：估值適用性段落新增原因導向提醒，涵蓋虧損、資料短、配息不穩、景氣循環、成長/低殖利率、配息率偏高、ETF 等情境。
  - 怎麼驗：`python -m unittest tests.test_rule_based_explain`、`python -m unittest discover -s tests`、紅線掃描回 `NO_MATCHES`。
- [x] 「30 秒看懂」/公司簡述用語擴充。
  - 2026-06-22 進度：`stock_brief_to_json()` 新增 `beginner_sentence` 與 `watch_items`，前端公司簡述會把新手閱讀順序接到既有摘要中。
  - 怎麼驗：`python -m unittest tests.test_web_api`、`node --check app/ui/static/app.js`、DOM-stub harness 呼叫 `renderCompanyBrief()` 印出 `OK`。
- [x] **每擴充一批字，補測試**：固定標題→固定分類/風險分數；確保不誤判、不灌爆、輸出不含紅線字（既有測試 `test_news_*`、`test_assessment` 可參考）。
  - 2026-06-22 進度：新增 `test_supply_chain_keyword_expansion`、`test_reporting_control_and_cybersecurity_expansion`、`test_payload_sanitizes_generated_reason_words`、`test_reporting_control_and_cybersecurity_risks`、`test_order_delay_risk_is_capped_per_term`。
  - 2026-06-22 進度：新增 `test_reason_specific_guidance_is_in_valuation_section`、`test_stock_brief_adds_beginner_sentence_and_watch_items`、`test_stock_brief_etf_route_uses_etf_language`。
  - 怎麼驗：`python -m unittest discover -s tests` 全綠（150 tests）。
- **驗收**：`python -m unittest discover -s tests` 全綠；新增字有測試；`contains_forbidden()` 對所有對外字串回空。

---

## 7. 建議執行順序

1. 先 **6.6**（擴字典，純後端 + 測試，低風險、立即有感）。
2. 再 **6.4**（K 線區間計算，純函數好驗）。
3. 再 **6.5**（教學/名詞，內容為主）。
4. 再 **6.1**（UI/排版細修 + 本地資料排序篩選）。
5. **6.2 / 6.3** 先各產出評估文件，最小落地（正式 server 唯讀版、PWA 殼）視時間再做——這兩個動到部署/隱私，務必保守、先寫 `docs/*-評估.md` 再動手。

> 每完成一項：跑 §3 全部驗證 → 綠 → 在本檔把 `- [ ]` 改 `- [x]` 並補「怎麼驗的」。卡關就保守處理、留 TODO，不要越紅線硬幹。
