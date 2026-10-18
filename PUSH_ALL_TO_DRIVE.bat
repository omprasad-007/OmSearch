@echo off
title OM Search - Push All Pages to Google Drive (5 TB)
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - PUSH ALL CRAWLED PAGES TO GOOGLE DRIVE (5 TB PLAN)
echo ========================================================================
echo.

py scripts\push_pages_to_drive.py
if %ERRORLEVEL% EQU 0 goto done

python scripts\push_pages_to_drive.py
if %ERRORLEVEL% EQU 0 goto done

python3 scripts\push_pages_to_drive.py
if %ERRORLEVEL% EQU 0 goto done

echo.
echo [!] Could not run Python script.
echo.
pause

:done
pause
