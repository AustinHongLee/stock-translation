# 風險評估報告（原始審查 + 修正追蹤）

- 範圍：`62e99eb`、`0b75ba2`、`d8c36f8`、`21634f1` 及其牽動的資料流。
- 原始狀態：main 與 origin/main 同步。**未 commit、未 push、未改 code。**
- 追蹤狀態：2026-06-23 已完成多批修正；原始審查內容保留作為風險來源，實際剩餘狀態以本節追蹤表與 `CODEX_HANDOFF_2.md` 為準。
- 作者立場：先找風險，再小步修正並驗證。修正順序見最後一節，已完成項不再重做。

---

## 0A. 2026-06-23 修正追蹤

已推送修正：
- `47c95c8 Address risk review data integrity issues`
- `7dfe01c Unify market target date handling`

| # | 現況 | 說明 |
|---|------|------|
| A1 | 已修 | 股利年度彙整抽到 `app/analyze/dividends.py`，已除息 TWT49U 與公告 T187AP45 不再重複加總。 |
| A4 | 已修 | 單檔同步改用 `upsert_dividend_records()`，增量同步不再清空既有歷史股利。 |
| A2 | 已修 | 數字年度與 ROC 季度可正確歸戶。 |
| A5 | 已修 | 股利彙整共用同一套去重/年度歸戶；T187AP45 若含法定盈餘公積/資本公積現金或轉增資，會在股利註記揭露組成口徑。 |
| C1/C2 | 已修 | SQLite 已加 WAL / `busy_timeout`；`/api/local-data`、`/api/sync/freshness` 改為唯讀覆蓋率計算，不在 GET 內寫 coverage。 |
| B1/B4 | 已修 | 新增 `MarketTargetDate`；本地資料、freshness、同步、法人同步都用 `target_latest_date`，舊快照不再靜默假裝最新。 |
| B2 | 已修 | 週末與 TWSE 官方休市日 target 會退到最近台股交易日；盤中/尚未收盤時沿用最近完成收盤日。 |
| B3 | 已修 | 已接入 TWSE 官方開休市資料 2024–2026，並補官方 row parser；缺口天數、target date 與 coverage hole_count 都共用台股交易日曆。未來年度待 TWSE 公布後再擴充。 |
| D1 | 已修 | 法人 T86 補正改用 TWSE 交易日曆，只查台股交易日；春節等長假不再累積成連續空日或多打休市日。 |
| E1 | 已修 | 低樣本歷史頻率不再顯示常態 100%/0% 面積。 |
| E2 | 已修 | 低樣本已降風險；「最近一日符合」已改成「近期出現」；常態區間對外文案改為「鐘形假設」，並加不代表後續走勢/不當成未來機率旁註。 |
| F1 | 已修 | 雷達/Excel/本地 UI 的「現價」已正名為「最近收盤」。 |
| F2 | 已修 | 新雷達 payload 不再產生 `current_price` 收盤 alias；舊快照仍會 backfill 成 `latest_close`，Excel fallback 保留舊檔相容。 |
| G1 | 已修 | 雷達中心與本地資料頁已明確區分：更新雷達只更新排行榜快照；全市場資料下載才補日線、法人與波段關卡。 |
| A3 | 已緩解 | TWT49U 歷史除權息明確只用「息值」作現金股利，並在個股頁/API/Excel 標註「權值不是每股股票股利」；歷史股票股利仍待可用官方每股配股來源。 |
| D2 | 已修 | 日線已最新時只跳過日線抓取，仍會刷新 profile、股利、估值、月營收與財報 metadata。 |
| D3 | 暫緩 | 日線按月重抓是效能成本，不是資料正確性錯誤。 |
| B5 | 已修 | post-check 若有寫入、但最新資料只落後目標 1 個台股交易日，歸為 `source_pending`；超過寬限才標 `suspect`。 |

目前下一步建議：
1. `A3` 若要完全修正，需另接可追溯每股股票股利的官方公告來源；目前已先防誤讀，不把 TWT49U 權值當股票股利。
2. `D3` 可暫緩：日線按月重抓是效能成本，不是資料正確性錯誤。

---

## 0. 一句話結論

資料「架構」方向是對的（覆蓋率索引、缺口規劃、收盤/盤中分層、免責文案都有在做），
但**股利計算有真的會算錯的 bug（雷達匯出 + 個股都中）**，而且**例行同步會把歷史股利清掉**；
另外**唯讀端點會寫資料庫**，在「全市場下載」進行中又開頁面時，很可能出現 `database is locked`。
這三件是要先處理的。其餘多為「假日沒算進去」「現價/收盤命名混淆」「低樣本統計看起來像預測」這類正確性與信任度問題。

---

## 1. 風險分級總表

| # | 風險 | 級別 | 主檔案 |
|---|------|------|--------|
| A1 | 雷達股利：同一年 TWT49U 與殘留 T187AP45 **重複加總** → 平均現金股利/殖利率/情境價偏高 | **P0** | `app/screener/value.py:548` |
| A4 | **增量同步會清空歷史股利**（先全刪、只補當年）→ 個股股利只剩當年 | **P0** | `app/sync/service.py:101`、`app/store/sqlite_store.py:372` |
| A2 | 股利年度判定：`period` 字串不符 → 某些年度的股利被整年漏算 | **P1** | `app/screener/value.py:553` |
| A3 | 歷史**股票股利系統性遺失**（TWT49U 只收「息」、跨來源去重又偏好它） | **P1** | `app/sync/twse.py:284`、`service.py:317` |
| C1 | 唯讀端點寫覆蓋率 + 多執行緒 server + 無 WAL/busy_timeout → `database is locked` | **P1** | `app/web/api.py:67,160`、`store:231`、`server.py:56` |
| C2 | `/api/local-data` 一次請求做 O(N) 寫入+commit+技術線計算 | **P1** | `app/web/api.py:54` |
| B1 | `target_date` 兩套定義（同步用 today、盤點用快照日）→ 同股不同頁狀態打架 | **P1** | `service.py:50` vs `api.py:66,159` |
| B2 | 假日/盤中下 target=today → 狀態抖成「待來源」；**假日完全沒處理** | **P1** | `data_gap.py:182,194` |
| B3 | business-day 計數**忽略台股國定假日** → hole_count/缺N日 長期假性偏高 | **P1** | `data_gap.py:182`、`store:1276` |
| D1 | 法人增量「連續 10 空日就停」→ 長假(農曆年)/停牌可能**提早停、漏抓** | **P1** | `app/sync/twse.py:503` |
| E1 | 回測低樣本（count=1）時「常態面積>0」顯示 **100%/0%**，像保證 | **P1** | `historical_frequency.py:454`、`app.js:2335` |
| F1 | 表格/Excel 欄位叫「現價」其實是**收盤快照** → 盤中/收盤分不清 | **P1** | `index.html:440`、`excel.py:131`、`value.py:182` |
| G1 | 「更新雷達」與「全市場資料下載」概念易混、且各自重抓全市場 | **P1** | `value.py:60`、`server.py:410` vs `bulk` |
| B4 | 「已最新」只代表跟**快照一樣新**；快照沒更新就會假裝最新 | **P1** | `api.py:159,186` |
| A5 | T187AP45 現金把「公積發放現金」一起加 → 與 TWT49U 定義不一致、破壞去重 | **P2** | `app/sync/twse.py:814` |
| D2 | 「current」早退會跳過 profile/估值/月營收/財報整包更新 | **P2** | `service.py:65` |
| D3 | 日線以「月」為單位抓，增量會重抓整月（idempotent，僅多耗網路） | **P2** | `app/sync/twse.py:100` |
| E2 | 常態68/95 + 面積 + 「最近一日符合」並列，整體**讀起來像預測** | **P2** | `app.js:2316`、`historical_frequency.py:20` |
| F2 | 內部命名 `current_price = close`，與盤中 `IntradayQuote.current_price` 同名異義 | **P2** | `value.py:158,182` |
| B5 | SUSPECT 門檻在半日市/來源延遲可能誤標健康資料為可疑 | **P2** | `data_gap.py:158` |

---

## 2. P0（會算錯 / 會掉資料，建議最先修）

### A1：雷達股利重複加總（測試員回報的「股利有誤」最可能根因）
`app/screener/value.py:541` `_annual_cash_dividends_by_year()`：

```python
ex_dividend_records = [r for r in year_records if r.source == "TWSE_TWT49U"]
if ex_dividend_records:
    annual_values[year] = sum(item.cash_dividend for item in year_records)  # ← 加總「全部」
    continue
```

- 跨來源去重 `_dedupe_dividend_records`（`value.py:520`）只用「金額相等(<0.01)」配對來丟掉 T187AP45。
- 只要 T187AP45 的現金金額**和 TWT49U 不完全相等**（很常見，見 A5：T187AP45 把公積現金也加進去），它就**不會被去重**，於是這裡 `sum(全部年record)` = TWT49U 現金 **＋** 殘留 T187AP45 現金 → **同一筆股利被加兩次**。
- 後果：`average_cash_dividend` 偏高 → `current_yield_percent`（估計殖利率）偏高 → 便宜/合理/昂貴情境價偏高。雷達匯出 Excel 的「近5年平均現金股利 / 估計現金殖利率% / 情境價」全部受影響。

### A4：增量同步會清空歷史股利（個股頁股利也會錯的根因）
`app/sync/service.py:101`：

```python
dividends.extend(self.client.fetch_historical_dividend_records(stock_id, start_date, fetch_end_date))
...
dividend_rows = self.store.replace_dividend_records(stock_id, dividends)
```

- `start_date = gap_plan.fetch_start_date`，在**增量同步**時 = 本地最後日+1（例如 2026-06-xx）。
- `fetch_historical_dividend_records` 以 `range(start.year, end.year+1)` 抓「年度除息」，所以增量時**只抓到今年**。
- `replace_dividend_records`（`store:372`）是**先 `DELETE FROM dividend_records WHERE stock_id=?` 再寫入**去重後的清單。
- 後果：使用者對一檔做「日線增量同步」後，**該股歷史股利被刪光，只剩當年那一兩筆**。個股「股利資料」分頁與殖利率估算因此忽多忽少 → 這就是你說的「資料集還是有亂的感覺」。
- 補充：就算第一次全抓，視窗也只回看 `lookback_days`(365) ≈ 1 年，所以歷史股利本來就很短、且高度依賴「上次同步的時間點」。

> P0 兩條合起來：雷達把股利**算多**、個股把股利**存少**，兩邊不一致，測試員一對就會發現。

---

## 3. P1（正確性 / 可靠性 / 信任度，建議接著修）

### A2 / A3：股利年度與股票股利
- `A2`：T187AP45 的 `period = 股利所屬年(季)度`（值像 `"112"`、`"112Q4"`），但 `value.py:553` 要 `period == "年度"` 或「含『季』且≥4 筆」才採計。**字面永遠不等於「年度」**，所以「只有 T187AP45、沒有 TWT49U」的年度會被整年丟掉 → 該年股利消失。
- `A3`：`fetch_historical_dividend_records` 只保留 `ex_right_type == "息"`（`twse.py:284`），`stock_dividend` 永遠 0；跨來源去重又偏好 TWT49U（`service.py:317`/`value.py:536`）。→ 歷史**股票股利**被系統性吃掉，Excel「股票股利」欄對舊年度不可信。

### C1 / C2：唯讀端點寫資料庫（架構 + 效能 + 鎖）
- `/api/local-data`（`server.py:140`→`api.py:54`）對**每一檔**已下載股票呼叫 `refresh_data_coverage` ×2（日線+法人），每次都 `INSERT … ON CONFLICT … ; commit()`（`store:854,816`）＋整表 MIN/MAX/COUNT＋`compute_support_resistance`。全市場下載完（~1000+ 檔）一次 cache-miss = **~2000 次寫入/commit + ~1000 次技術線計算**塞在一個請求裡。
- `/api/sync/freshness/<id>`（`server.py:145`）每次 GET 也寫 2 列覆蓋率、**且沒有快取**；前端開個股、批次補波段都會打它。
- 關鍵放大器：`StockTranslatorServer(ThreadingHTTPServer)`（`server.py:56`）多執行緒、每請求各開一條 `sqlite3.connect()`（`store:231`，**沒有 `journal_mode=WAL`、沒有 `busy_timeout`**），而「全市場下載」是常駐背景執行緒持續寫入（`bulk.py:73`）。
- 後果：**下載進行中（這正是使用者會一直看頁面的時候）只要開「本地資料」或任一檔個股，背景寫 + 前景寫互撞 → 立即 `database is locked` 例外、請求失敗。** 這也是「讀取卡頓/有時壞掉」的結構性來源。

### B1 / B2 / B3 / B4：缺口與假日
- `B1` 兩套 target：同步用 `date.today()`（`service.py:50`），盤點/freshness 用 value_screener 快照的 `price_date`（`api.py:66,159`）。同一股可能在「本地資料頁」顯示已最新、按「同步」卻又說有缺口 → 反直覺。
- `B2` 假日/盤中：同步 target=today，週末/國定假日/收盤前都會 `latest(週五) < today` → 判 gap → 抓空 → 標 `source_pending`。`previous_business_day`（`data_gap.py:194`）只跳週末、且沒被用來定 target；**國定假日完全沒處理**。
- `B3` business-day 計數（`data_gap.py:182`、`store:1276`）只排除六日。於是 `hole_count = 工作日數 - 實際筆數` 會把每年 ~13–15 個國定假日全算成「洞」→ 任何一年資料都顯示一堆缺漏；前端「缺 N 日」（`app.js:5110`）也偏多。這直接影響你問的「資訊健康」判讀。
- `B4` 「已最新」只表示**跟快照一樣新**（`api.py:186`）。若沒按「更新雷達」更新 `value_screener.json`，快照停在舊日期 → 全部顯示「已最新」其實落後好幾天（靜默過期）。

### D1：法人增量可能漏抓
`fetch_institutional_trades`（`twse.py:459`）由近往遠逐日打 T86，`consecutive_empty >= 10` 就 break（`:503`），且 `max_days = max(20, gap+5)` 上限。農曆年（連假常 ≥9 個日曆日、跨多個平日）或個股停牌時，**連續空日可能在抵達真正有資料的日期前就觸發提前停止**，造成更舊的法人日永遠補不回來（`skip_dates` 只跳已知日，不會幫你越過空洞）。

### E1：回測低樣本顯示 100%/0%
`summarize_forward_returns`：count==1 → `stdev=0` → `_normal_area_above_zero` 回 100 或 0（`historical_frequency.py:454`）。卡片照樣顯示「常態面積>0 = 100%」配「1 次」（`app.js:2335`）。對小白這看起來=「保證上漲」。建議：樣本 < 8（或 20）時隱藏 `normal_*` 欄位，只留次數與分位數。

### F1：「現價」其實是「收盤」
- 雷達/本地資料表頭「現價」（`index.html:440`）、Excel 表頭「現價」（`excel.py:131,232`）對應的是 `item.current_price`，而它 = `price.close`（收盤快照，`value.py:182`）。
- 周邊文案卻一直寫「最近收盤快照」。**同一個數字一邊叫現價、一邊叫收盤** → 這就是你說的盤中/收盤分不清。個股頁本身是對的（`display_price_label="最近收盤"`、另有獨立「盤中報價」區）。
- 建議：把這些「現價」改名為「最近收盤」或「收盤(資料日)」。

### G1：「更新雷達」vs「全市場資料下載」易混
- 「更新雷達」(`/api/value-screener/refresh`→`value.py:60`) 自己向 TWSE 抓**全市場** profiles/prices/dividends，寫進 `value_screener.json` 快照。
- 「全市場資料下載」(`bulk`) 把**全市場**日線+法人寫進 sqlite。
- 兩者都對全市場連線、卻塞進**不同儲存**，彼此關係不透明，使用者不知道該先按哪個、也不知道兩邊資料日可能不一致 → 流程反直覺 + 重複抓取。

---

## 4. P2（打磨 / 技術債 / 措辭）

- **A5**：T187AP45 現金 = 盈餘 + 法定盈餘公積 + 資本公積（`twse.py:814-822`），TWT49U 是單一「現金股利」。定義不一致 → 破壞 A1 的金額去重、也可能讓「現金股利」比一般認知偏高。建議統一定義。
- **D2**：日線 `current` 早退（`service.py:65`）會跳過 profile/估值(BWIBBU)/月營收/財報整包。價穩定但月營收/財報剛出時不會更新。
- **D3**：日線以「月」抓（`twse.py:100`），增量重抓整月；upsert 冪等所以正確，只是多耗網路。
- **E2**：常態 68/95 區間 + 面積 + 「最近一日符合」並列（`app.js:2316`），整體讀起來像預測；模組層免責寫得很好（`historical_frequency.py:20`），但**每張卡缺即時旁註**、且「最近一日符合」措辭偏強。
- **F2**：`current_price` 命名一名兩義（收盤 vs 盤中），是 F1 的技術債根源。
- **B5**：SUSPECT 規則（寫了列但沒到 target）在半日市/來源延遲時可能誤標健康資料為可疑。

---

## 5. 直接回答你的幾個問題（小白向）

### 5.1 盤中資訊 vs 收盤資訊：一個簡單規則
> **原則：所有「分析、估價、排行、法人、技術線、回測」一律用「收盤(日線)」；「盤中」只用在『現在大概多少錢』這一個即時瞄一眼的場景。**

| 你想看的東西 | 該用哪種 | 理由 |
|---|---|---|
| 殖利率、便宜/合理/昂貴情境價 | **收盤** | 要穩定、可重現；盤中會一直跳 |
| 雷達排行、漲跌榜、成交值/量 | **收盤快照** | 全市場一致的同一天 |
| 支撐/壓力、KD/RSI、歷史回測 | **收盤** | 技術指標定義就是收盤 |
| 三大法人買賣超 | **收盤後**(約16:00才出) | 盤中根本還沒有 |
| 「現在股價大概多少」 | **盤中報價** | 只有這個需要即時 |

目前程式其實**已經是這樣分層**（盤中只在個股頁的「盤中報價」區、用 `fetch_intraday_quote`），問題只出在**命名**：很多地方把「收盤」叫成「現價」（F1/F2）。先把字改對，你的「亂」會少一大半。

### 5.2 資料到底有沒有不完整？
有，主要三處：
1. **歷史股利會被增量同步清掉**（A4）→ 看起來忽多忽少。
2. **歷史股票股利幾乎都缺**（A3）。
3. **法人在長假附近可能漏抓**（D1）；**月營收/財報在價格沒變動時不會更新**（D2）。

### 5.3 雷達匯出股利為什麼會錯？
就是 **A1（算多）** + **A2/A3（年度漏算、股票股利缺）**。個股頁則是 **A4（被清空）**。兩邊用不同程式算同一件事、又各自有 bug，所以對不起來。

### 5.4 怎麼「加快讀取」又「確保完整/健康」？
方向（這次不動手，只列給你/Codex 決策）：
1. **把覆蓋率改成『寫入時更新』**：同步/下載完成後才寫 `data_coverage`；`/api/local-data`、`/api/sync/freshness` 改用唯讀的 `get_data_coverage` + 記憶體內算 gap（消滅 C1/C2）。
2. **SQLite 開 WAL + `busy_timeout`**（例如 5000ms）：根治下載中開頁面的 `database is locked`。
3. **單一「最近交易日」來源**（含國定假日表）取代到處用的 `date.today()`／快照日（解 B1/B2/B3/B4）。
4. **股利計算抽成一份、修好去重與年度歸戶**（解 A1–A5），雷達與個股共用同一套。

---

## 6. 建議修正順序（先後）

1. **A4**（停止清空歷史股利）— 影響最大、最容易讓人對數字失去信任；可先把 `replace_dividend_records` 改成 upsert、或讓歷史股利抓取不受增量視窗限制。
2. **A1 + A2 + A3 + A5**（股利計算整包修對，雷達/個股共用）。
3. **C1 + C2**（唯讀端點別寫庫 + 開 WAL/busy_timeout）— 解「下載中會壞」。
4. **F1 + F2**（「現價」正名為「收盤」）— 低成本、直接解你「盤中/收盤分不清」。
5. **B1–B4**（單一最近交易日來源 + 國定假日表）。
6. **D1**（法人提前停止條件改用「交易日」而非連續空日；或用市場有交易日清單驅動）。
7. **E1 + E2**（低樣本隱藏常態值 + 每卡旁註）。
8. **G1**（兩個「更新」按鈕的文案/關係講清楚，或合併流程）。

### 可以先不做（暫緩）
- **D3**（按月重抓）：冪等、僅多耗網路，等效能真的有感再說。
- **D2**（current 早退跳過財報）：可加「財報/月營收另排程」而非現在改。
- 回測的多重比較校正（E2 延伸）：屬統計嚴謹度，非錯誤。

---

## 7. 不改 code 也能複現/驗證的方式

- **A4**：對一檔已有多年股利的股票，先看個股股利分頁筆數 → 按「同步」→ 再看，筆數會掉到只剩當年。
- **A1**：找一檔同年有「除息(TWT49U)」又有「T187AP45 公告」、且兩者現金金額不完全相等的股票，雷達「平均現金股利」會明顯比實際高。
- **C1**：開始「全市場資料下載」，同時不斷重整「本地資料」頁/開個股 → 觀察是否出現 `database is locked`（可看 `data/ui_*server*.err.log`）。
- **B2/B3**：週末或國定假日當天按「同步」→ 狀態會變「待來源」；本地資料「缺 N 日」會比實際交易日數多。

---

*本報告僅為審查結論，未變更任何程式碼，未 commit、未 push。*
