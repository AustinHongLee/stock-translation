# 股票翻譯機 — Codex 作業手冊（第二輪）

> 第一輪 24 項已完成、171 測試通過。**本輪主軸：從「衝廣度」轉成「正確、穩固、深度」**，再加一個旗艦交付（一鍵研究報告）。
> 沿用第一輪 `CODEX_HANDOFF.md` 的 **§1 紅線**、**§2 架構地圖**、**§3 驗證指令／前端 harness**——本檔不重抄，只補本輪重點。動工前先做 §0 commit。

---

## 0. 先做：把第一輪成果存檔（commit）

你目前 `git status` 還有一批 modified/untracked。先把它存起來，別讓一整輪成果只躺在工作區。

- [x] 看 `git status` / `git diff`，**分 2–4 個有意義的 commit**（依功能群組，例如「K線區間統計」「教學/名詞擴充」「新聞字典擴充」「PWA/評估文件」），message 寫清楚做了什麼。
- [x] 確認 `.gitignore` 有生效：`dist/`、`build/`、`data/*.sqlite3`、`data/value_screener.json` **不在** diff 內。
- [x] 若已設 `origin` 就 push；沒設或沒權杖就停在 commit、留給人工 push（不要硬塞憑證）。
- **驗收**：`git status` 乾淨、`git log --oneline` 有清楚紀錄；GitHub 上沒有 `dist/`、`.sqlite3`。
  - 2026-06-22 驗證：第一輪已拆成 `f374ac9 Add analysis and glossary coverage`、`3a9dcb1 Add PWA UI and sync workflow`、`c8d706f Document Codex handoffs`，並成功 `git push origin main`；`git rev-parse HEAD origin/main` 相同。`git diff --name-status` 未包含 `dist/`、`build/`、`data/*.sqlite3`、`data/value_screener.json`。

---

## 1. 紅線（不變，違反即 bug）— 摘要

完整見第一輪 §1。重點不變：
- **不預測股價、不報明牌、不買賣建議、不下單。**
- UI／分析層禁字：`便宜價/合理價/昂貴價/低估/高估/該買/該賣/會漲/會跌/建議買進賣出`（同事版 Excel「傳統估價表」是唯一例外）。
- **紅綠只用於漲跌事實**；籌碼/體質/支撐壓力用 藍/琥珀/灰。
- **規則式、不接 LLM**；純函數、可測。隱私本地不上傳。
- 任何「結論／解讀／統計」都要**附資料日期 + 免責**。

> 紅線掃描（應為空；`docs/`、`*HANDOFF*.md` 不算）：
> `grep -rnE "便宜價|合理價|昂貴價|低估|高估|該買|該賣|會漲|會跌" app/ui app/analyze app/chips app/news app/explain`

---

## 2. 驗證（每改必驗，沿用第一輪 §3）

```bash
python -m unittest discover -s tests        # 全綠（含本輪新增 golden 測試）
node --check app/ui/static/app.js           # 前端語法
python -m compileall app tests              # 編譯掃描
# 前端 runtime：用第一輪 §3 的 DOM-stub harness 餵假資料呼叫改到的函式，確認不丟錯
```
**本輪額外門檻**：新計算一定要有「黃金測試」（固定輸入→已知輸出對照），不能只靠「跑得動」。

---

## 3. 本輪主軸：穩固 ＞ 廣度

第一輪把功能面鋪得很廣了。本輪**先把正確性與穩定鎖死，再深化少數功能，最後做旗艦報告**。新增表面積要克制，重點是「可信賴」。

---

## 4. 任務

### A. 資料正確性 ＋ 黃金測試（最優先）

> 前面踩過 RSI（簡單平均 vs Wilder）、支撐壓力（被單一漲停綁架）兩個算錯的雷。本組目的是**讓所有計算都被測試鎖死、壞資料不會污染**。

- [x] **指標黃金測試補滿**：RSI(Wilder)、KD(9,3,3)、乖離、SMA、價格位階、體質等級門檻——各用固定數列 + 對照值（含外部參考，如 StockCharts RSI≈70.5）鎖死。
- [x] **levels（波撐/波壓）黃金測試**：固定 OHLC → 固定樞紐與「接近波撐/波壓/區間中/資料不足」；務必含「孤立漲停不被當壓力」案例。
- [x] **valuation_bands**：固定輸入 → 固定百分位/區間/位階。
- [x] **壞資料防護**：收盤 0、缺漏日、整列相同（漲跌停）、停牌列，**不可污染** MA/RSI/KD/河流圖/支撐壓力；各補一個「丟壞資料也算對」的測試。
- [x] **單位/格式稽核**：張 vs 股、百分比 vs 小數，在 UI、tooltip、Excel 匯出一致；不一致就修並加測試。
- **驗收**：unittest 全綠且**明顯多出 golden 測試**；紅線掃描空。
  - 2026-06-22 驗證：新增/強化 `tests/test_assessment.py`、`tests/test_levels.py`、`tests/test_valuation_bands.py`、`tests/test_health_analysis.py`、`tests/test_chips_institutional.py`，總測試由 171 增至 180。已跑 `python -m unittest discover -s tests`（180 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`，紅線掃描 `app/ui app/analyze app/chips app/news app/explain` 為 `NO_MATCHES`。本次只改純函數與測試，無前端視覺變更。

### B. 穩固、錯誤處理、效能

- [x] **一鍵下載：續傳持久化**——把進度（已完成股票清單、已抓 T86 日期）寫進 DB/檔，**重啟程式後真正接續**（目前靠資料存在與否間接續傳，做成顯式記錄更可靠）。
- [x] **下載：只重試失敗清單**——後端端點 + 前端按鈕，針對 `failed` 清單重跑，不必整批重來。並加 **ETA 估計**（用已完成速率推估）。
- [x] **`/api/local-data` 效能**：全市場上千檔時不要每次請求重算所有 sr。改成在**下載完成時算一次並快取**（或加 TTL 快取），UI 只讀；大量資料下不可卡。
- [x] **狀態一致化**：載入中/無資料/抓取失敗/離線，全站用同一套元件與文案；TWSE 失敗要優雅降級並明示「資料可能不完整」。
- [x] **`app.js` 體質**（單檔約 3800+ 行）：先「**分區註解 + 評估能否安全模組化**」（拆成多個 `<script>` 檔、無打包器）；有把握再拆，每步 `node --check` + harness。沒把握就只整理分區、別硬拆。
- **驗收**：關掉重開能續傳（可驗）；只重試失敗可運作；local-data 大量資料下順；harness 過。
  - 2026-06-22 驗證：新增 SQLite `bulk_progress`（股票/T86 日期）與 `app_cache`，`/api/bulk-download/status` 會合併 persisted progress；`/api/bulk-download/retry-failed` 只重跑 failed 清單；bulk status 回傳 `eta_seconds/items_per_minute`。`/api/local-data` 改 TTL cache，個股同步與批次完成會清 cache。`app.js` 加分區地圖，暫不拆檔，並讓本地資料讀取失敗走 `stateMessageHTML("error")`。已跑 `python -m unittest discover -s tests`（185 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、紅線掃描 `NO_MATCHES`。前端截圖驗證：桌面 `C:/Users/a0976/AppData/Local/Temp/stock-bulk-desktop.png`；手機 `C:/Users/a0976/AppData/Local/Temp/stock-bulk-mobile.png`，並修正手機換行後 bulk 小按鈕高度一致。
  - 2026-06-23 驗證（雷達/本地資料互動）：把「全市場資料下載」從雷達中心搬到「本地資料」頁；雷達中心改標「最近收盤排行」與「收盤資料日」，保留股利情境、高殖利率觀察、殖利率需複查排行。所有 `data-screener-stock` 的「看個股」改成只讀本地 `loadStock()`，不再觸發 `/api/sync`；仍保留列內「更新」才同步波段目標。已跑 `python -m unittest discover -s tests`（206 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、`git diff --check`、共通紅線掃描 `NO_MATCHES`。前端截圖驗證：雷達 `C:/Users/a0976/AppData/Local/Temp/stock-radar-recent-close.png`、殖利率榜 `C:/Users/a0976/AppData/Local/Temp/stock-radar-yield-rankings.png`、本地資料下載 `C:/Users/a0976/AppData/Local/Temp/stock-local-data-download.png`；Playwright 攔截確認點雷達「看個股」只打 `GET /api/stocks/2545?days=365`，`/api/sync` 呼叫為空。
  - 2026-06-23 驗證（同步 freshness + 雷達快照排行）：新增 `/api/sync/freshness/{stock_id}`，單檔同步與批次同步都支援 `skip_if_current`，本地日線日期已到雷達最近收盤時直接回本地 payload，不跑抓取；前端按「同步」會先檢查 freshness，波段多檔更新也會統計「已是最近收盤」的 skipped 檔數。雷達中心新增「收盤快照排行」：成交值、成交量、開盤跳空、日內震幅；`load_value_screener()` 會為舊格式 JSON 回填可衍生排行，更新雷達後會寫入完整新欄位。另修正個股 header 在按鈕多時把公司全名擠成直排的排版問題。已跑 `python -m unittest discover -s tests`（209 OK）、`node --check app/ui/static/app.js`、`python -m compileall app`、`git diff --check`、行首衝突標記/`debugger`/`console.log` 掃描皆無命中。前端截圖驗證：雷達快照排行 `C:/Users/a0976/AppData/Local/Temp/stock-radar-snapshot-ranks-complete.png`、跳空/震幅下半段 `C:/Users/a0976/AppData/Local/Temp/stock-radar-snapshot-ranks-complete-lower.png`、同步跳過提示與 header 修正 `C:/Users/a0976/AppData/Local/Temp/stock-sync-freshness-skip-toast.png`。
  - 2026-06-23 驗證（資料缺口補正）：新增 `data_coverage` 索引表與 `app/analyze/data_gap.py`，日線與三大法人同步會先用本地最新日、雷達最近收盤日回算缺口，只補缺的交易日；小缺口走增量補正，過大缺口才轉重建，抓完後再做 post-check，若來源未給資料會標 `source_pending/suspect` 而不是無限重抓。本地資料頁新增「資料狀態」欄，同時顯示日線與法人缺口；`/api/sync` skip 分支也回傳 `gap/coverage`，可診斷為什麼沒重抓。已跑 `python -m unittest discover -s tests`（219 OK）、`node --check app/ui/static/app.js`、`python -m compileall app tests`、`git diff --check`、行首衝突標記/`debugger`/`console.log` 掃描皆無命中。API 驗證：`/api/sync/freshness/2330` 回 `daily_status=current`、`institutional_status=gap`；`POST /api/sync` with `skip_if_current=true` 回 `skipped=true`、`gap_status=current`、`coverage_latest=2026-06-22`。前端截圖驗證：本地資料狀態欄 `C:/Users/a0976/AppData/Local/Temp/stock-local-data-coverage.png`。
  - 2026-06-23 驗證（Opus 風險修正第一批）：新增 `RISK_REVIEW_2026-06-23.md` 作為審查紀錄；修正 P0 股利鏈：股利年度彙整抽到 `app/analyze/dividends.py`，雷達、個股估值、估價適用性共用同一套規則，TWT49U 已除息資料不再和 T187AP45 年度公告重複加總，數字年度/ROC 季度可正確歸戶；單檔同步與全市場下載改用 upsert 股利，不再因增量同步刪掉歷史股利。另修正 P1/P2：SQLite 連線加 `busy_timeout`/WAL；`/api/local-data`、`/api/sync/freshness` 改為唯讀計算覆蓋率、不在 GET commit；服務層週末 target 退到最近工作日；法人 T86 連續空日閥門放寬到最多 20 個交易日；雷達/Excel「現價」正名為「最近收盤」；歷史頻率低樣本不再顯示常態 100%/0% 面積。已跑 `python -m unittest discover -s tests`（227 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、`git diff --check`、行首衝突標記/`debugger`/`console.log` 掃描皆無命中。前端截圖驗證：雷達最近收盤語意 `C:/Users/a0976/AppData/Local/Temp/stock-riskfix-radar-close-label.png`。
  - 2026-06-23 驗證（最近收盤目標 / 快照過期防護）：新增 `app/analyze/market_calendar.py`，把「雷達快照日期、快照產生日、預估最近收盤日」統一成 `MarketTargetDate`；`/api/sync/freshness`、單檔同步、批次同步、法人同步、本地資料頁都改用 `target_latest_date`，雷達快照若落後超過容忍交易日且快照本身也未近期確認，會改以最近完成交易日做補正目標，不再把舊快照誤判成已最新。本地資料 payload 新增整體 `data_target`，摘要改成「檢查日 / 最近收盤目標」，並將 local-data cache key bump 到 `local_data_v2`，避免舊 schema 快取讓 UI 缺目標日。已跑 `python -m unittest discover -s tests`（234 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`。前端截圖驗證：本地資料目標日摘要 `C:/Users/a0976/AppData/Local/Temp/stock-market-target-local-data-final.png`。
  - 2026-06-23 驗證（2026 台股休市日）：新增 `app/analyze/twse_calendar.py`，將 TWSE 2026 休市日接入 `count_business_days()`、`previous_business_day()` 與新增的 `next_business_day()`；資料缺口補正會跳過 2026 國定假日，6/19 端午休市不再被算成缺 1 日，增量抓取也會從下一個交易日開始。`RISK_REVIEW_2026-06-23.md` 已改成原始審查 + 修正追蹤，標出 B3 目前是「部分修」，後續仍需官方 CSV/多年度交易日曆。已跑 `python -m unittest tests.test_data_gap tests.test_market_calendar tests.test_sync_service tests.test_web_api tests.test_local_data`（31 OK）、`python -m py_compile app/analyze/twse_calendar.py app/analyze/data_gap.py app/analyze/market_calendar.py app/sync/service.py`。
  - 2026-06-23 驗證（日線 current 仍刷新 metadata）：`StockSyncService.sync_stock_history()` 改成先刷新 profile、股利、估值、月營收、財報 metadata；若日線已到 target，只跳過 `fetch_daily_prices()`，不再整包早退。已補測試確認價格 range 不會被打、但 profile/估值/月營收/財報仍寫入。已跑 `python -m unittest tests.test_sync_service tests.test_data_gap tests.test_web_api`（24 OK）、`python -m py_compile app/sync/service.py`。

### C. 深化既有功能（挑著做，研究型先出文件）

- [x] **基本面趨勢**：毛利率/營益率/淨利率/ROE 多季小折線（純資料呈現，不下結論）。
- [x] **自選股看板**：watchlist 一覽表，每檔顯示 漲跌 / 體質總評燈號 / 地雷狀態 / 波段關卡，一眼掃過。
- [x] **多股比較**：2–3 檔 價格 / 三大法人 / 體質 對比視圖。
- [x] **上櫃 TPEx 覆蓋**（先寫 `docs/tpex-評估.md`）：上櫃的日線/法人/估值來源與 TWSE 差異、要改哪些 client 方法。
- [x] **ETF v2**（先寫 `docs/etf-評估.md`）：成分股、折溢價、追蹤指數、配息頻率的資料來源與可行性。
- **驗收**：每個功能有純函數 + 測試；研究型先交評估文件再動手。
  - 2026-06-22 驗證（基本面趨勢）：新增 `app/analyze/fundamental_trends.py` 純函數，把多季財報整理成毛利率、營益率、淨利率、單季 ROE 四條序列；`build_stock_payload()` 回傳 `fundamental_trends`。個股頁「基本面：獲利能力」新增四張 SVG 小折線卡，只呈現歷史百分比與前季變動，不下結論。已跑 `python -m unittest discover -s tests`（192 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、紅線掃描 `NO_MATCHES`。前端截圖驗證使用暫存 demo DB（不改正式資料）：桌面 `C:/Users/a0976/AppData/Local/Temp/stock-fundamental-trends-desktop.png`；手機 `C:/Users/a0976/AppData/Local/Temp/stock-fundamental-trends-mobile.png`。
  - 2026-06-22 驗證（自選股看板）：新增 `app/analyze/watchlist_board.py` 純函數，`/api/watchlist` 每檔回傳 `board`（漲跌、本地體質燈號、本地地雷狀態、波段關卡）；首頁自選股卡片改成三格狀態看板。地雷狀態只整理本地已同步資料，新聞地雷仍需進個股頁抓取。已跑 `python -m unittest discover -s tests`（195 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、紅線掃描 `NO_MATCHES`。前端截圖驗證：桌面 `C:/Users/a0976/AppData/Local/Temp/stock-watchlist-board-desktop.png`；手機 `C:/Users/a0976/AppData/Local/Temp/stock-watchlist-board-mobile.png`，並修正手機自選股看板不再被雙欄擠壓。
  - 2026-06-22 驗證（多股比較）：新增 `app/analyze/stock_compare.py` 純函數與 `/api/compare?stock_ids=...`，首頁新增「多股比較」表單，可輸入或套用自選股前 3 檔；比較列顯示價格、近 20 日三大法人、本地體質、最新財報點與資料日期。手機版改成每檔一張緊湊比較列，避免橫向表格第一眼看不到體質/財報。已跑 `python -m unittest discover -s tests`（200 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、紅線掃描 `NO_MATCHES`。前端截圖驗證：桌面 `C:/Users/a0976/AppData/Local/Temp/stock-compare-desktop-crop.png`；手機 `C:/Users/a0976/AppData/Local/Temp/stock-compare-mobile-crop.png`，瀏覽器 console error 為空。
  - 2026-06-23 驗證（TPEx 評估）：新增 `docs/tpex-評估.md`，只做研究文件未改程式。已查 TPEx OpenAPI swagger、個股日成交資訊、三大法人買賣明細資訊，確認上櫃歷史日線 API、法人歷史 action、估值/營收/財報候選端點與 TWSE client 差異；特別標出成交仟股/仟元需乘 1000、法人欄位重複、財報產業格式與歷史股利來源不足。已跑 `git diff --check`。
  - 2026-06-23 驗證（ETF v2 評估）：新增 `docs/etf-評估.md`，只做研究文件未改程式。已查 TWSE ETF 頁面/OpenAPI、TPEx ETF 訊息中心、SITCA ETF 專區，整理商品基本資料、淨值折溢價、配息頻率、追蹤指數與成分股/PCF 的可行性；第一版建議先做 ETF 專用頁與 profile/nav/dividend，成分股先保留官方連結。已跑 `git diff --check`。

### D. 旗艦：一鍵個股研究報告（HTML / PDF 匯出）

> 高價值、把現有東西整合成一份能丟給測試者/同事看的報告。

- [x] 把 **體質總評 + 三大法人 + 估值情境 + 消息/地雷雷達 + 價量摘要（含區間統計）+ 重點名詞教學** 整理成一份乾淨報告（HTML 優先，可選 PDF）。
- [x] 個股頁一鍵匯出；**每段標資料日期，整份附免責，全程不得有買賣建議**。
- **驗收**：報告產出成功、版面乾淨；內容無紅線字；數字與頁面一致。
  - 2026-06-22 驗證：新增 `app/exporters/html_report.py` 純函數產 HTML 報告，後端 `/api/export/stocks/{id}.html` 會整合個股 payload 與新聞 payload；新聞來源失敗時降級但不讓報告失敗。個股頁 header 與資料來源區新增「研究報告 / 匯出研究報告」入口。已跑 `python -m unittest discover -s tests`（188 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、紅線掃描 `NO_MATCHES`。前端截圖驗證：桌面個股頁 `C:/Users/a0976/AppData/Local/Temp/stock-report-desktop.png`；手機個股頁 `C:/Users/a0976/AppData/Local/Temp/stock-report-mobile.png`；HTML 報告頁 `C:/Users/a0976/AppData/Local/Temp/stock-report-html.png`。截圖驗證時修正 `price_position` 0~1 顯示成 1.0% 的口徑問題，報告頁現在與個股頁一致顯示約 98%。

### E.（可選、務必謹慎）事實頻率回測

> 回應之前的「玄學」需求，但**用歷史事實呈現、絕不變成預測**。

- [x] 「歷史頻率」而非勝率：例如「近一年內，KD 低檔黃金交叉出現 N 次；當時其後 5／20 個交易日的**漲跌分布**為 …」——**純歷史統計**，明確標「過去不代表未來、不保證重演、不是買賣建議」。
- [x] 先寫設計（門檻、視窗、措辭、免責），再做純函數 + 測試；UI 收在教學/進階區。
- **驗收**：輸出全是歷史事實 + 強免責；`contains_forbidden()` 對所有對外字串回空；有測試。
  - 2026-06-23 驗證（事實頻率回測）：新增 `app/analyze/historical_frequency.py` 純函數，固定 KD 低檔交叉、RSI 低位回升、收回月線、接近波撐、爆量收紅、高檔過熱等事件，只統計事件後 5/20 個交易日的歷史報酬分布；輸出樣本數、正報酬比例、平均/中位數、分位數、樣本標準差、常態 68%/95% 區間與常態面積 >0，UI 收在個股頁「歷史頻率回測」摺疊區並標示「樣本分布 · 非預測」。已跑 `python -m unittest discover -s tests`（204 OK）、`node --check app/ui/static/app.js`、`node --check app/ui/static/sw.js`、`python -m compileall app tests`、`git diff --check`、共通紅線掃描 `NO_MATCHES`、2330 `historical_frequency` payload `contains_forbidden()` 回 `[]`。前端截圖驗證：桌機 `C:/Users/a0976/AppData/Local/Temp/stock-historical-frequency-desktop.png`；手機 390px `C:/Users/a0976/AppData/Local/Temp/stock-historical-frequency-mobile.png`，手機 `overflowX=0`。

---

## 5. 每項任務的驗收門檻（共通）

`unittest` 全綠（含新 golden）→ `node --check` → `compileall` → harness OK → 紅線掃描空 → **新計算有測試** → 數字與資料日期一致 → 在本檔把 `- [ ]` 改 `- [x]` 並補「怎麼驗的」。

---

## 6. 建議執行順序

1. **§0 commit**（先存檔）。
2. **A 正確性/黃金測試**（鎖死前一輪成果，最高 CP 值）。
3. **B 穩固/效能**（續傳、只重試失敗、local-data 快取）。
4. **D 旗艦報告**（看得到的價值）。
5. **C 深化**（基本面趨勢 → 自選股看板 → 多股比較 → TPEx/ETF 先評估）。
6. **E 事實頻率**（有餘力再做，最謹慎）。

> 守則同第一輪 §5：小步快驗、純函數優先、單檔 app.js 維持有效、守紅線、卡關就保守留 TODO 不硬幹。完成一項就勾選並記「怎麼驗的」，讓人回來能看進度。
