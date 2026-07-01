@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo 股票翻譯機 - 套用官方資料包
echo.
echo 這會把此版本隨包附的公開市場資料補進你的本機資料庫。
echo 原則：只新增缺的資料，不覆蓋、不刪除，也不碰自選股、持倉、圖表標註或設定。
echo.

if not exist "股票翻譯機.exe" (
  echo 找不到「股票翻譯機.exe」。請把這個檔案放在程式資料夾內再執行。
  echo.
  pause
  exit /b 1
)

"股票翻譯機.exe" --apply-seed --no-open
echo.
echo 完成。若上方顯示新增 0 筆，代表你的本機資料已經有這份資料包能補的內容。
echo.
pause
