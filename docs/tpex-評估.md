# 上櫃 TPEx 覆蓋評估

檢查日：2026-06-23

本文件只評估資料源與實作切法，不先實作程式。目標是讓目前只支援上市 TWSE 的同步流程，後續能安全擴充到上櫃 TPEx，且不破壞既有紅線：不預測、不報明牌、不提供買賣建議，所有呈現都保留資料日期與來源。

## 目前程式假設

目前同步核心集中在 `app/sync/twse.py` 的 `TwseClient`，`StockSyncService` 與 `bulk_runner` 直接依賴它。現況有幾個上市市場假設：

- 股票清單只抓 TWSE `/opendata/t187ap03_L`，寫入 `StockProfile.market="TWSE"`。
- 日線歷史使用 TWSE `STOCK_DAY`，成交量與成交值已是股數/元口徑。
- 批次下載 prelude 只抓上市清單、上市營收、上市財報、上市估值、上市法人 T86。
- 法人資料用 TWSE T86 固定欄位位置解析。
- 財報 parser 預期上市欄名，例如 `年度`、`季別`、`公司代號`、`資產總額`。

因此 TPEx 不適合直接塞進 `TwseClient` 分支。建議新增市場路由層，讓 TWSE 與 TPEx 各自維持 parser 與 source tag。

## 已確認的官方來源

| 需求 | 官方來源 | 可行性 | 注意事項 |
|---|---|---:|---|
| 上櫃基本資料 | TPEx OpenAPI `/openapi/v1/mopsfin_t187ap03_O` | 高 | 欄位偏英文，如 `SecuritiesCompanyCode`、`CompanyName`；要轉成 `StockProfile(market="TPEX")`。 |
| 最新全市場行情 | TPEx OpenAPI `/openapi/v1/tpex_mainboard_quotes` | 高 | `Date` 是民國年 compact，例如 `1150618`；成交量/金額欄名不同於 TWSE。 |
| 歷史單股日線 | TPEx `www/zh-tw/afterTrading/tradingStock?code={stock_id}&date={YYYY/MM/01}&response=json` | 高 | 頁面說自民國 83 年 1 月起提供。欄位為 `成交仟股`、`成交仟元`，寫入 `DailyPrice.volume/trade_value` 前必須乘 1000。 |
| 三大法人最新明細 | TPEx OpenAPI `/openapi/v1/tpex_3insti_daily_trading` | 中高 | 欄位名稱很長且有空白/拼字差異，要用 alias map。 |
| 三大法人歷史明細 | TPEx `www/zh-tw/insti/dailyTrade?type=Daily&sect=AL&date={YYYY/MM/DD}&response=json` | 中 | 已測 JSON 可回資料，但不是 OpenAPI swagger 路徑；要用 fixture 監控欄位漂移。頁面說本資訊自民國 96 年 4 月 20 日起提供。 |
| 本益比/殖利率/PBR | TPEx OpenAPI `/openapi/v1/tpex_mainboard_peratio_analysis` | 高 | 最新全市場資料，可對應 `MarketValuation`。 |
| 每月營收 | TPEx OpenAPI `/openapi/v1/mopsfin_t187ap05_O` | 高 | 欄位多數接近 TWSE t187ap05，但 source tag 要分開。 |
| 損益表 | TPEx OpenAPI `/openapi/v1/mopsfin_t187ap06_O_ci` | 中高 | 只涵蓋一般業。銀行、金控、保險等另有 `_bd/_fh/_ins/_mim/_basi`。 |
| 資產負債表 | TPEx OpenAPI `/openapi/v1/mopsfin_t187ap07_O_ci` | 中高 | 同上，需依產業/報表類型路由。 |
| 除權息每日計算 | TPEx OpenAPI `/openapi/v1/tpex_exright_daily` | 中 | 偏當日計算結果；要補歷史股利時，不能直接等同 TWSE `t187ap45_L` + `TWT49U`。 |

官方入口：

- [TPEx OpenAPI Swagger](https://www.tpex.org.tw/openapi/)
- [TPEx 個股日成交資訊](https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html)
- [TPEx 三大法人買賣明細資訊](https://www.tpex.org.tw/zh-tw/mainboard/trading/major-institutional/detail/day.html)

## 實測重點

歷史日線範例：

`https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code=3105&date=2024%2F08%2F01&response=json`

回傳重點：

- `stat: "ok"`
- `date: "20240801"`
- `tables[0].fields`: `日 期, 成交仟股, 成交仟元, 開盤, 最高, 最低, 收盤, 漲跌, 筆數`
- row 日期是民國年斜線，例如 `113/08/01`
- 成交量與成交值必須乘 1000；這是最容易造成錯誤的差異。

三大法人歷史範例：

`https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=AL&date=2026%2F06%2F18&response=json`

回傳重點：

- `stat: "ok"`
- `date: "20260618"`
- 欄位是多層表頭攤平後的 `買進股數/賣出股數/買賣超股數` 重複欄名；parser 不能只靠欄名，要用表頭順序 fixture 鎖住。
- `sect=EW` 可排除權證/牛熊證；若只做股票與 ETF，建議先用 `EW` 或後處理過濾證券代號。

## 建議實作切法

1. 新增 `TpexClient`，不要把 TPEx 分支塞進 `TwseClient`。
2. 抽出共用 parser：民國 compact 日期、民國斜線日期、數字清理、空值處理。
3. 新增市場路由，例如 `MarketDataClient` protocol 或 `CompositeMarketClient`：
   - 已知 `StockProfile.market` 時依 market 選 client。
   - 不知道市場時先查本地 profile；仍未知才查 TWSE/TPEX profile。
4. `fetch_otc_profiles()` 寫入 `StockProfile.market="TPEX"`。
5. `sync_stock_history()` 依市場呼叫 client，但維持相同 store 寫入模型。
6. 批次下載 prelude 改成 TWSE + TPEx 兩套清單與共用檔，各自記錄錯誤；不要讓 TPEx 加值資料失敗阻斷 TWSE。
7. 日線 parser 明確命名單位轉換，例如 `parse_thousand_shares_to_shares()`，並在 golden test 固定 3105 樣本。
8. 法人 parser 用固定欄位位置 + source fixture，不依賴重複欄名。
9. 財報第一版先支援一般業 `_ci`，金融/保險/金控等報表類型列為 phase 2。
10. 股利資料第一版只整合可確認的除權息每日資料；歷史股利分派需另找穩定來源後再接。

## 測試清單

- `tests/test_tpex_client.py`
  - profile: `/mopsfin_t187ap03_O` 樣本轉 `StockProfile(market="TPEX")`
  - daily history: `tradingStock` 樣本，確認 `成交仟股/仟元` 乘 1000
  - latest quote: `/tpex_mainboard_quotes` 樣本轉 `DailyPrice`
  - valuation: `/tpex_mainboard_peratio_analysis` 樣本轉 `MarketValuation`
  - institutional: OpenAPI 樣本 + `dailyTrade` 樣本各一組
  - revenue/financial: `mopsfin_t187ap05_O`、`t187ap06_O_ci`、`t187ap07_O_ci`
- `tests/test_sync_market_routing.py`
  - 已知 `market="TWSE"` 不呼叫 TPEx
  - 已知 `market="TPEX"` 不呼叫 TWSE
  - 未知股票在 profile 探測後能寫入正確 market
- `tests/test_bulk_runner.py`
  - prelude 同時建立 TWSE/TPEX bulk items
  - TPEx 加值資料失敗時 TWSE 清單仍可繼續

## 風險與保守界線

- TPEx 網頁 action 不是 OpenAPI 合約，雖然可回 JSON，但要用 fixture 與錯誤訊息保護。
- TPEx 法人欄位重複且 OpenAPI key 有不一致空白，必須 alias map。
- 日線成交量/成交值單位不同，若漏乘 1000，會直接污染量價分析。
- 財報不同行業報表型態不同，第一版不要假裝全產業都完整。
- ETF 代號第六碼 K/C 的交易單位與幣別註記要保留在 note，不要直接套普通股單位。
- 歷史股利分派還沒有找到與 TWSE `t187ap45_L` 完全對等的 TPEx 來源；第一版不要補推。

## 第一版完成定義

- 上櫃股票能被搜尋/同步，profile market 顯示為 `TPEX`。
- 上櫃個股頁能顯示日線、體質、關卡、估值、營收、一般業財報與資料日期。
- 法人資料可按日/近 N 日同步，遇網頁 API 變動時顯示「資料暫不可用」而不是中斷整個同步。
- 所有 source tag 分開，例如 `TPEX_TRADING_STOCK`、`TPEX_3INSTI_DAILY`。
- golden tests 覆蓋單位轉換與法人欄位，不只測能跑。
