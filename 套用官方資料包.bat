@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo 股票翻譯機 - 套用官方資料包
echo.
echo 這會從 GitHub 下載最新官方資料包，再補進你的本機資料庫。
echo 原則：只新增缺的資料，不覆蓋、不刪除，也不碰自選股、持倉、圖表標註或設定。
echo.

if not exist "股票翻譯機.exe" (
  echo 找不到「股票翻譯機.exe」。請把這個檔案放在程式資料夾內再執行。
  echo.
  pause
  exit /b 1
)

"股票翻譯機.exe" --apply-data-hub --no-open
if errorlevel 1 goto fail
echo.
echo 完成。若上方顯示新增 0 筆，代表本機已經有最新官方資料。
echo.
pause
exit /b 0

:fail
echo.
echo 套用失敗。請確認網路可連到 GitHub 後再試一次；原本資料不會被刪除。
echo.
pause
exit /b 1
