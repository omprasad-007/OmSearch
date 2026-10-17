@echo off
title OM Search - Push to GitHub and Google Drive
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - ONE-CLICK COMPLETE SYNC (GOOGLE DRIVE + GITHUB)
echo ========================================================================
echo.
echo [1/2] Pushing all crawled pages and archives to Google Drive (5 TB)...
echo ------------------------------------------------------------------------
py scripts\push_pages_to_drive.py
if %ERRORLEVEL% NEQ 0 (
    python scripts\push_pages_to_drive.py
)

echo.
echo [2/2] Pushing latest code and crawler data to GitHub...
echo ------------------------------------------------------------------------
call PUSH_TO_GITHUB.bat

echo.
echo ========================================================================
echo   [✓] ALL TASKS COMPLETE: DRIVE UPLOAD & GITHUB SYNC FINISHED!
echo ========================================================================
echo.
pause
