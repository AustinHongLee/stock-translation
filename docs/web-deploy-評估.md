# 網頁化評估

日期：2026-06-22

## 結論

目前這套系統適合「本機單人使用」。若要網頁化，第一步只能做**公開資料唯讀站**：查股、雷達中心、名詞解釋、新聞與報價這類公開資料可以開；持倉、交易紀錄、自選股、同步/下載控制與匯出個人資料都不能直接公開。

建議路線：

1. 保留現有 `app.web.server` 當本機版。
2. 另開 `app.web.public_asgi` 當公開唯讀版。
3. 公開版預設只讀本地 SQLite 快取與公開資料端點；所有 POST/PUT/DELETE 都拒絕。
4. 若未來要多人登入，再新增帳號、權限、個人資料隔離與背景同步佇列，不要把本機版端點直接外放。

## 現況限制

- `app.web.server` 使用 `ThreadingHTTPServer`，適合本機工具，不是正式對外 server。
- 沒有認證、授權、CSRF、防暴力請求、rate limit 或 HTTPS 終止設定。
- 本地 SQLite 內含個人持倉、自選股、交易紀錄；多人對外時不能混在同一份資料。
- `POST /api/sync`、`/api/institutional/sync`、`/api/bulk-download/*` 會打 TWSE 或啟動長工作，不適合被公開請求直接觸發。
- TWSE 資料來源有速率與穩定性限制，公開站應使用背景快取，不要每個 request 即時抓。
- Excel 匯出含持倉或個股工作簿；公開版必須先區分個人資料與公開資料後再開放。

## 方案比較

### A. 正式框架 + ASGI/WSGI

可用 FastAPI/Flask，但目前專案依賴很少，為了最小落地，可以先提供低階 ASGI `app`，讓 `uvicorn app.web.public_asgi:app` 能跑。等 API 契約穩定後，再決定是否引入 FastAPI。

優點：部署邊界清楚，可以跟本機版分離。

風險：若直接共用本機 server route，會誤開個人資料與寫入端點。

### B. 唯讀公開資料站

只開：

- `GET /`
- `GET /static/*`
- `GET /api/glossary`
- `GET /api/search`
- `GET /api/stocks/{stock_id}`
- `GET /api/quotes/{stock_id}`
- `GET /api/value-screener`
- `GET /api/local-data`
- `GET /api/local-stocks`
- `GET /api/daily-price`
- `GET /api/news/{stock_id}`

持倉與自選股 GET 回空資料，避免 UI 壞掉但不洩漏個人資料；所有寫入與同步端點拒絕。

優點：最安全、最接近現況可落地。

風險：UI 仍會顯示一些本機功能按鈕，後續應加「公開唯讀模式」前端旗標，把持倉/同步/自選相關入口淡出或改文案。

### C. 自架單人用

可把本機版放到自己內網/VPN 後面，但仍要有基本認證與 HTTPS，且只能自己用。

優點：改動少。

風險：一旦暴露到公網，持倉與交易紀錄就是明文 API。

## 必備工程

- 路由分離：本機版與公開版分開 entrypoint。
- 個人資料隔離：持倉、交易、watchlist 不得出現在公開版 payload。
- 背景快取：TWSE 抓取改由背景 job 更新 SQLite 或快取檔，前台 request 只讀。
- 寫入保護：公開版 POST/PUT/DELETE 預設拒絕。
- 靜態資源 cache：公開部署可加長 cache，但 API 保持 no-store。
- 錯誤頁與 JSON 錯誤格式：404/405/500 一致。
- 基本資安：HTTPS、反向代理、rate limit、request size limit、log 去識別化。

## 最小落地定義

本輪最小落地只做：

- 新增 `app.web.public_asgi:app`。
- 提供公開唯讀 GET API。
- `GET /api/portfolio` 與 `GET /api/watchlist` 回空資料，不讀取本地個人資料。
- POST/PUT/DELETE 回 405，不執行同步、交易或寫入。
- 可用 `uvicorn app.web.public_asgi:app --host 127.0.0.1 --port 8766` 本機啟動。

驗收：

- 單元測試證明公開版不洩漏持倉/自選資料。
- 本機用 ASGI callable 直接 smoke test。
- 既有本機版測試全綠。
