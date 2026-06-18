# Sync Module

責任：唯一接觸外部股市資料源的模組。

目前 W1 實作：

- `twse.py`：證交所資料轉接器，將官方 JSON 轉成內部 `DailyPrice` / `StockProfile`。
- `service.py`：同步服務，負責呼叫轉接器並寫入本地 store。

邊界：

- UI 不得呼叫本目錄。
- 分析層不得呼叫本目錄。
- 對外輸出只使用 `app.models` 的資料契約。

