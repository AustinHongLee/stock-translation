@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo 股票翻譯機 - 重新取得完整官方資料
echo.
echo 這個舊檔名保留給已經習慣使用它的測試者。
echo 現在改用安全模式：下載 GitHub 最新官方資料，只補缺口，
echo 不再覆蓋整個資料庫，也不會清掉自選股、持倉、提醒、標註或設定。
echo.

if not exist "股票翻譯機.exe" (
  echo 找不到「股票翻譯機.exe」。請確認 zip 已完整解壓縮。
  echo.
  pause
  exit /b 1
)

"股票翻譯機.exe" --apply-data-hub --no-open
if errorlevel 1 goto fail

echo.
echo 完成。請重新開啟「股票翻譯機」。
echo.
pause
exit /b 0

:fail
echo.
echo 套用失敗。請確認網路可連到 GitHub 後再試一次；原本資料不會被刪除。
echo.
pause
exit /b 1
