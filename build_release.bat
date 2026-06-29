@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Building Stock Translator portable release...
echo.

for /f "usebackq delims=" %%V in (`python -c "from app.version import APP_VERSION; print(APP_VERSION)"`) do set "APP_VERSION=%%V"
if "%APP_VERSION%"=="" goto fail
set "APP_DIR=dist\股票翻譯機"
set "ZIP_PATH=dist\StockTranslator-v%APP_VERSION%.zip"
set "SHA_PATH=%ZIP_PATH%.sha256"

python tools\make_app_icon.py
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean stock_translator.spec
if errorlevel 1 goto fail

if not exist "%APP_DIR%\data" mkdir "%APP_DIR%\data"
copy /Y "data\stock_translator.sqlite3" "%APP_DIR%\data\stock_translator.sqlite3" >nul
copy /Y "data\stock_catalog.json" "%APP_DIR%\data\stock_catalog.json" >nul
copy /Y "data\value_screener.json" "%APP_DIR%\data\value_screener.json" >nul
copy /Y "README_給測試者.txt" "%APP_DIR%\README_給測試者.txt" >nul

python tools\package_release.py "%APP_DIR%" "%ZIP_PATH%" "%SHA_PATH%"
if errorlevel 1 goto fail

echo.
echo Done: %ZIP_PATH%
echo SHA-256: %SHA_PATH%
echo Upload both files to the GitHub Release for tag v%APP_VERSION%.
exit /b 0

:fail
echo.
echo Build failed.
exit /b 1
