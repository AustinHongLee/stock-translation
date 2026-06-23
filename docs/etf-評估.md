# ETF v2 評估

檢查日：2026-06-23

本文件只評估 ETF v2 的資料源、可行性與實作順序，不先實作程式。ETF v2 的定位應是「資料整理與風險揭露」，不是排名、推薦或買賣提示。

## 目標與邊界

ETF v2 建議先補四類資料：

- 商品基本資料：名稱、類型、發行公司、追蹤指數/主動式策略、幣別、交易市場。
- 淨值與折溢價：收盤價、淨值、折溢價比率、資料時間。
- 配息資料：配息紀錄、預計/實際頻率、配息來源提示。
- 成分/投資範圍：成分股或主要投資範圍，但第一版不強行保證每檔都有機器可抓的完整持股。

不能做的事：

- 不依配息率、折溢價或成分股集中度給出買賣結論。
- 不把高配息寫成較好，也不把折溢價解讀成進出場提示。
- 不用第三方聚合站當主要資料源；若要暫用只能標明非官方且不可進入核心同步。

## 官方來源盤點

| 需求 | 官方來源 | 可行性 | 注意事項 |
|---|---|---:|---|
| 上市 ETF 清單 | TWSE RWD `/rwd/zh/ETF/domestic?response=json` 與同系列 ETF 分類頁 | 中高 | 已確認國內成分股 ETF 清單可回 JSON；其他分類端點有防直連/redirect，需逐類測試。 |
| 上市 ETF 商品資訊 | TWSE 商品資訊頁 `/zh/products/securities/etf/products/content.html?{code}=` | 中 | 頁面可查商品內容，但 `productContent` 直連測試被擋；第一版可當人工驗證，不建議當穩定批次來源。 |
| TWSE OpenAPI ETF | TWSE OpenAPI `/ETFReport/ETFRank` | 低 | 目前只看到定期定額排行，不足以支援商品基本資料、淨值或成分股。 |
| 上市 ETF 即時淨值/折溢價 | TWSE 基本市況報導網站 ETF 淨值揭露專區 | 中 | 官方教學指向 `mis.twse.com.tw/stock/etf_nav.jsp?ex=tse`；需另做瀏覽器/API 探查，不宜先寫死。 |
| 上櫃 ETF 商品與淨值折溢價 | TPEx ETF 訊息中心商品頁 | 中 | 前端 JS 使用 `/ETF/api/etfProduct?lang=zh-tw&query={code}`，頁面包含商品欄位、配息、近 2 個月淨值與折溢價；shell 直連會被導到安全頁，需用瀏覽器或後續確認可接受的請求方式。 |
| 上櫃 ETF 交易行情 | TPEx OpenAPI `/tpex_mainboard_quotes` 或 ETF 訊息中心 | 中高 | 行情可沿用 TPEx 市場資料；ETF 類別需由 profile/list 過濾。 |
| 開放式基金 | TPEx OpenAPI `/tpex_opfund_latest` 等 | 低 | 是開放式基金行情，不等於上市/上櫃 ETF v2 主目標。 |
| 配息觀念與風險措辭 | 投信投顧公會 ETF 專區、TWSE ETF 總覽 | 高 | 適合做免責與名詞教學，不是同步數值來源。 |
| 成分股/PCF | ETF 發行投信官網、公開說明書、TWSE ETF 商品頁連結 | 中低 | 各發行商格式不同，第一版建議只保留外部連結與「待接發行商 adapter」。 |

官方入口：

- [TWSE ETF 總覽](https://www.twse.com.tw/zh/page/ETF/intro.html)
- [TWSE 國內成分股 ETF](https://www.twse.com.tw/zh/products/securities/etf/products/domestic.html)
- [TWSE ETF 商品資訊範例](https://www.twse.com.tw/zh/products/securities/etf/products/content.html?0050=)
- [TWSE OpenAPI](https://openapi.twse.com.tw/)
- [TPEx ETF 訊息中心商品頁範例](https://info.tpex.org.tw/ETF/zh/detail.html?query=00740B)
- [TPEx ETF 商品分類](https://www.tpex.org.tw/zh-tw/product/etf/overview/categories.html)
- [SITCA ETF 投資百寶箱](https://www.sitca.org.tw/ROC/SITCA_ETF/etf-hub-product.html)
- [SITCA ETF 知識篇](https://www.sitca.org.tw/ROC/SITCA_ETF/etf-hub-knowledge.html)

## 建議資料模型

新增模型時先保持扁平，避免一開始就做過度完整的基金資料庫：

- `EtfProfile`
  - `stock_id`
  - `name`
  - `short_name`
  - `market`: `TWSE` 或 `TPEX`
  - `category`: 國內股票、海外股票、債券、槓桿/反向、主動式等
  - `issuer`
  - `manager`
  - `underlying_index`
  - `strategy`
  - `currency`
  - `source`
  - `source_updated_at`
- `EtfNavSnapshot`
  - `stock_id`
  - `date`
  - `market_price`
  - `nav`
  - `premium_discount_percent`
  - `estimated_nav`
  - `source`
- `EtfDividend`
  - `stock_id`
  - `ex_date` 或 `pay_date`
  - `amount`
  - `frequency_label`
  - `source`
  - `note`
- `EtfHoldingLink`
  - `stock_id`
  - `url`
  - `source`
  - `note`

成分股若要入庫，建議 phase 2 再新增 `EtfHolding`，因為不同發行商 PCF/持股揭露格式差異很大。

## 第一版 UI 建議

ETF 個股頁不要沿用普通股票的體質/財報語氣。建議分成：

1. 商品資訊：ETF 類型、追蹤指數或主動式策略、發行公司、幣別、市場。
2. 淨值與折溢價：只顯示事實與資料日期，附「市價可能偏離淨值」說明。
3. 配息紀錄：列歷史紀錄與頻率標籤，提示配息不等同總報酬。
4. 成分/投資範圍：若無機器可抓成分，先放官方商品頁/發行商連結。
5. 風險提醒：集中度、流動性、折溢價、追蹤誤差、匯率、槓桿/反向單日目標。

普通股票頁可繼續使用體質、法人、估值；ETF 頁要改成 ETF 專用模組，避免把 EPS、ROE、PBR 等公司財報指標套到基金商品。

## 實作順序

1. 建立 ETF 辨識：由 TWSE/TPEx profile 或 ETF 清單判斷 `asset_type="ETF"`。
2. 新增 `EtfClient` facade，底下分 `TwseEtfClient`、`TpexEtfClient`、未來發行商 adapter。
3. 第一階段只做 profile + quote + nav/premium + dividend summary，不做完整成分股。
4. 建立 ETF 專用 payload，讓個股頁依 `asset_type` 切換版面。
5. 成分股先放官方連結；若後續要入庫，先挑 1 家發行商做 adapter 與 fixture，不要一次支援所有投信。
6. 補 golden fixture：
   - TWSE ETF 清單樣本
   - TPEx ETF 商品頁 payload 樣本
   - 淨值/折溢價樣本
   - 配息紀錄樣本
7. 紅線測試：ETF 所有對外字串不可出現買賣提示或暗示排名。

## 風險與保守界線

- TWSE 商品內容與 MIS 淨值揭露可能需要瀏覽器 session 或特殊 header；不要在第一版承諾全自動。
- TPEx ETF 訊息中心 API 不是 OpenAPI 合約，若接入要用 fixture 監控欄位漂移。
- 配息頻率不等於商品好壞；UI 只顯示頻率與歷史紀錄。
- 折溢價是風險資訊，不是操作訊號。
- 主動式 ETF 可能沒有追蹤指數，資料模型要允許 `underlying_index=None`。
- 槓桿/反向 ETF 強調單日目標，不能用長期累積報酬與標的指數做簡化比較。
- 成分股/PCF 來源高度分散，第一版以官方連結與少量 adapter 逐步擴充。

## 第一版完成定義

- ETF 能被辨識並走 ETF 專用頁，不套普通股票財報體質。
- 至少 TWSE 國內成分股 ETF 與 TPEx ETF 樣本各有一組 golden fixture。
- 頁面顯示商品基本資料、行情、淨值/折溢價、配息紀錄與資料日期。
- 成分股若無穩定機器來源，顯示官方外部連結與「尚未同步成分資料」。
- 所有 ETF 文案通過紅線掃描與 `contains_forbidden()` 類測試。
