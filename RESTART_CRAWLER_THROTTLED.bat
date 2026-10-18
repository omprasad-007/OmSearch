@echo off
title OM Search - Restart Crawler (Throttled 500-600 docs/sec)
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - RESTART CRAWLER WITH SPEED THROTTLED TO 500-600 DOCS/SEC
echo ========================================================================
echo.

echo [+] Stopping previous crawler processes...
powershell -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*run_continuous_drive_ingestion.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[✓] Stopped Process ID ' + $_.ProcessId) }"

timeout /t 1 >nul 2>&1

echo [+] Removing stop signal files if present...
del /f /q data\STOP_CRAWLER STOP_CRAWLER >nul 2>&1

echo [+] Launching throttled continuous ingestion daemon (500-600 docs/sec)...
wscript START_LIVE_CRAWLER_SILENT.vbs

timeout /t 2 >nul 2>&1

echo.
echo ========================================================================
echo   [✓] SUCCESS: Crawler restarted at 500-600 documents per second!
echo ========================================================================
echo.
pause
