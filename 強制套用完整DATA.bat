@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo 股票翻譯機 - 強制套用完整 DATA
echo.
echo 這是測試員救援用批次檔，會把此版本隨包附的完整官方 data 放進：
echo %%LOCALAPPDATA%%\StockTranslator\data
echo.
echo 注意：
echo 1. 請先完全關閉「股票翻譯機」。
echo 2. 這會覆蓋本機 stock_translator.sqlite3、stock_catalog.json、value_screener.json。
echo 3. 覆蓋前會先備份原本 data；自選股、持倉、標註若存在於原 DB，也會留在備份裡。
echo 4. 官方 data 已清掉打包者的自選股、持倉、標註與本機快取。
echo.

set "SOURCE_DATA=%~dp0official_data\data"
if not exist "%SOURCE_DATA%\stock_translator.sqlite3" (
  echo 找不到官方完整 DATA：%SOURCE_DATA%
  echo 請確認 zip 已完整解壓縮，不要只單獨拿這個 bat。
  echo.
  pause
  exit /b 1
)

if "%LOCALAPPDATA%"=="" (
  echo 找不到 LOCALAPPDATA 環境變數，無法判斷資料要放哪裡。
  echo.
  pause
  exit /b 1
)

set "TARGET_ROOT=%LOCALAPPDATA%\StockTranslator"
set "TARGET_DATA=%TARGET_ROOT%\data"
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "STAMP=%%T"
if "%STAMP%"=="" set "STAMP=backup"
set "BACKUP_DATA=%TARGET_ROOT%\data_backup_%STAMP%"

echo 來源：%SOURCE_DATA%
echo 目標：%TARGET_DATA%
echo 備份：%BACKUP_DATA%
echo.
choice /C YN /N /M "確定要覆蓋本機 DATA 嗎？輸入 Y 繼續，N 取消："
if errorlevel 2 goto cancelled

if not exist "%TARGET_ROOT%" mkdir "%TARGET_ROOT%"

if exist "%TARGET_DATA%" (
  echo.
  echo 正在備份原本 DATA...
  robocopy "%TARGET_DATA%" "%BACKUP_DATA%" /E /R:2 /W:1 >nul
  if errorlevel 8 goto backup_failed
)

if not exist "%TARGET_DATA%" mkdir "%TARGET_DATA%"

echo.
echo 正在覆蓋為官方完整 DATA...
robocopy "%SOURCE_DATA%" "%TARGET_DATA%" /E /R:2 /W:1 >nul
if errorlevel 8 goto copy_failed

echo.
echo 完成。請重新開啟「股票翻譯機」。
if exist "%BACKUP_DATA%" echo 原本資料備份在：%BACKUP_DATA%
echo.
pause
exit /b 0

:cancelled
echo.
echo 已取消，沒有改動本機 DATA。
echo.
pause
exit /b 0

:backup_failed
echo.
echo 備份失敗，未繼續覆蓋。請確認股票翻譯機已關閉，或把錯誤畫面截圖回報。
echo.
pause
exit /b 1

:copy_failed
echo.
echo 覆蓋失敗。原本資料備份在：%BACKUP_DATA%
echo 請確認股票翻譯機已關閉，或把錯誤畫面截圖回報。
echo.
pause
exit /b 1
