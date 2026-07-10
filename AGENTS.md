## Imported Claude Cowork project instructions

## Stock Translator local project instructions

- Before changing anything related to data fetching, stock sync, full-market download, quiet background sync, local-data status, radar refresh, seed/official data packs, or legacy import, read `docs/00-AGENT必讀_資訊抓取整合定義.md` first.
- Keep the fetching contract unified: external market data enters through `app/sync`, persistence goes through `SQLiteStore`, and daily-price decisions must use `app/analyze/data_gap.py` rather than ad hoc UI/server checks.
- Do not push unless the user explicitly asks.
