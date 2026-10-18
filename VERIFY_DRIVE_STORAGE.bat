@echo off
title OM Search - Verify Google Drive Storage
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - GOOGLE DRIVE STORAGE ^& UPLOAD VERIFICATION
echo ========================================================================
echo.

py scripts\diagnose_gdrive.py
if %ERRORLEVEL% EQU 0 goto done

python scripts\diagnose_gdrive.py
if %ERRORLEVEL% EQU 0 goto done

python3 scripts\diagnose_gdrive.py
if %ERRORLEVEL% EQU 0 goto done

echo.
echo [!] Could not run Python. Please ensure Python is installed.
echo.

:done
echo.
pause
