# Store Module

責任：本地 SQLite 資料庫讀寫。

邊界：

- 外部 API 回應不得直接流進 UI；必須先轉成 `app.models`，再透過 store 寫入。
- 其他模組只能透過 `SQLiteStore` 的公開方法讀寫，不直接碰 schema 細節。

目前核心表：

- `stock_profiles`：股票基本資料。
- `daily_prices`：日線價格。
- `sync_runs`：同步紀錄。

