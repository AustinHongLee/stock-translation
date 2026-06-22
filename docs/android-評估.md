# Android / APP 化評估

日期：2026-06-22

## 結論

建議先走 **PWA**，再視需要包 WebView 殼。不要第一步就重寫原生 Android，因為目前前端已是完整本機 Web App，後端又是 Python + SQLite；原生化成本高，而且資料同步、TWSE 限速、個人持倉隔離都還需要先解。

優先路線：

1. 先完成 RWD（已在 §6.1 補手機寬度）。
2. 做 PWA：manifest + service worker，先支援「可安裝」與靜態資源快取。
3. 資料仍走 API；不要把股價/持倉資料塞進 service worker cache。
4. 若要上架或更像 App，再用 WebView/TWA/Capacitor 包同一份前端，後端指向 §6.2 的公開唯讀 ASGI 版或自架後端。

## 方案比較

### A. PWA

優點：

- 最小改動，沿用目前 HTML/CSS/JS。
- 可安裝到桌面或 Android 主畫面。
- service worker 可快取 app shell，提升再次開啟速度。
- 適合公開唯讀站與自架單人站。

限制：

- 本機 Python server 不會直接跑在一般 Android 手機上。
- 離線只能開 app shell；股價、雷達、新聞仍需要 API。
- 若要推播、背景同步或上架商店，需要更多工程。

### B. WebView / TWA / Capacitor

優點：

- 可包成 APK/AAB。
- 能接 Android 原生能力，例如檔案、分享、通知。
- TWA 適合把已部署的 HTTPS PWA 包成商店 App。

限制：

- 後端仍要遠端化或自架；不能假設手機能跑這個 Python server。
- 要處理登入、憑證、版本更新與 WebView 相容性。

### C. 原生 Android

不建議作為近期路線。這會重寫 UI、圖表、資料同步與持倉流程，成本遠高於收益，而且容易讓 Web 版與 App 版邏輯分叉。

## 後端難點

- Python + SQLite 適合桌面本機；Android 直接跑 Python server 需要 Chaquopy/BeeWare 類方案，成本與穩定性都不適合 MVP。
- 若要多人或手機遠端使用，後端要走 §6.2：公開唯讀 ASGI 版、個人資料隔離、背景快取、認證與 rate limit。
- 個人持倉不能放進公開 API；若未來做登入，必須每個使用者資料分離。

## 本輪最小落地

本輪做 PWA 基礎：

- `manifest.webmanifest`
- `sw.js`
- app icon 192 / 512
- `index.html` 加 manifest/theme-color/icon
- `app.js` 註冊 service worker
- 本機 server 與 public ASGI server 都能從根路徑提供 `/manifest.webmanifest` 與 `/sw.js`

Service worker 策略：

- app shell 靜態資源 cache-first。
- `/api/` 一律走 network，不快取資料。
- 安裝失敗不影響桌面版一般使用。

驗收：

- manifest JSON 合法、icon 檔存在。
- service worker 含 app shell cache 且排除 API cache。
- 桌面版測試全綠。
