@echo off
title OM Search - Autonomous Live Crawler (2500+ docs/sec)
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - HIGH-SPEED AUTONOMOUS CRAWLER (2500+ DOCS/SEC)
echo   Cloud Archive: Google Drive (1,000,000 documents per mega-batch)
echo   Throughput:    2500+ documents per second
echo ========================================================================
echo.

echo [+] Stopping any previous crawler instances...
powershell -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*run_continuous_drive_ingestion.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[✓] Stopped Process ID ' + $_.ProcessId) }"

echo [+] Removing stop signals...
del /f /q data\STOP_CRAWLER STOP_CRAWLER >nul 2>&1

echo.
echo [+] Launching high-speed ingestion (2500+ docs/sec, 1M pages per Drive batch)...
py scripts\run_continuous_drive_ingestion.py --batch-size 2500 --crawl-threads 8
if %ERRORLEVEL% EQU 0 goto done

python scripts\run_continuous_drive_ingestion.py --batch-size 2500 --crawl-threads 8
if %ERRORLEVEL% EQU 0 goto done

python3 scripts\run_continuous_drive_ingestion.py --batch-size 2500 --crawl-threads 8
if %ERRORLEVEL% EQU 0 goto done

echo.
echo [!] Could not locate Python. Please ensure Python is installed.
echo.
pause

:done
