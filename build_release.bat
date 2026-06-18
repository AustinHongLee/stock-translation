@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Building Stock Translator portable release...
echo.

python tools\make_app_icon.py
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean stock_translator.spec
if errorlevel 1 goto fail

if not exist "dist\股票翻譯機\data" mkdir "dist\股票翻譯機\data"
copy /Y "data\stock_translator.sqlite3" "dist\股票翻譯機\data\stock_translator.sqlite3" >nul
copy /Y "data\stock_catalog.json" "dist\股票翻譯機\data\stock_catalog.json" >nul
copy /Y "data\value_screener.json" "dist\股票翻譯機\data\value_screener.json" >nul
copy /Y "README_給測試者.txt" "dist\股票翻譯機\README_給測試者.txt" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'dist\股票翻譯機測試版.zip') { Remove-Item 'dist\股票翻譯機測試版.zip' -Force }; Compress-Archive -Path 'dist\股票翻譯機\*' -DestinationPath 'dist\股票翻譯機測試版.zip' -Force"
if errorlevel 1 goto fail

echo.
echo Done: dist\股票翻譯機測試版.zip
echo Send this zip to testers.
exit /b 0

:fail
echo.
echo Build failed.
exit /b 1
