@echo off
title OM Search - Sync Crawled Pages into Search Engine
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - RE-INDEX ALL CRAWLED PAGES INTO SEARCH ENGINE DATABASE
echo ========================================================================
echo.

py scripts\reindex_all_crawled_pages.py
if %ERRORLEVEL% EQU 0 goto done

python scripts\reindex_all_crawled_pages.py
if %ERRORLEVEL% EQU 0 goto done

python3 scripts\reindex_all_crawled_pages.py
if %ERRORLEVEL% EQU 0 goto done

echo.
echo [!] Could not locate Python. Please ensure Python is installed.
echo.

:done
echo.
pause
