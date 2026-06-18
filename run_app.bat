@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Stock Translator UI...
echo.
echo Stopping old local server if it is still running...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$servers = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*app.web.server*' }; foreach ($server in $servers) { Stop-Process -Id $server.ProcessId -Force }" >nul 2>nul
timeout /t 1 /nobreak >nul
python -B -m app.web.server --host 127.0.0.1 --port 8765 --db data\stock_translator.sqlite3 --open
echo.
pause
