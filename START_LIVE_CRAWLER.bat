@echo off
title OM Search - Autonomous Live Crawler
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - 24/7 AUTONOMOUS WEB CRAWLER ^& DRIVE CLOUD ARCHIVE
echo ========================================================================
echo.
echo Target: Continuous real-time document crawling and Drive archiving
echo Telemetry: Automatically updates data\drive_ingestion_live_status.json
echo.
del /f /q data\STOP_CRAWLER STOP_CRAWLER >nul 2>&1

py scripts\run_continuous_drive_ingestion.py
if %ERRORLEVEL% EQU 0 goto done

python scripts\run_continuous_drive_ingestion.py
if %ERRORLEVEL% EQU 0 goto done

python3 scripts\run_continuous_drive_ingestion.py
if %ERRORLEVEL% EQU 0 goto done

echo.
echo [!] Could not locate Python or py launcher.
echo [!] Please ensure Python is installed from python.org or Microsoft Store.
echo.
pause

:done
