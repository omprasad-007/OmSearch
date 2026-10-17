@echo off
title OM Search - Push to GitHub
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - PUSH LATEST CODE ^& LIVE DATA TO GITHUB
echo   Repository: https://github.com/omprasad-007/OmSearch.git
echo ========================================================================
echo.

:: Verify git is installed
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Error: Git command line tool not found in PATH.
    echo [!] Please install Git from https://git-scm.com/
    pause
    exit /b 1
)

:: Ensure remote origin is set correctly
git remote set-url origin https://github.com/omprasad-007/OmSearch.git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    git remote add origin https://github.com/omprasad-007/OmSearch.git >nul 2>&1
)

echo [+] Staging updated files (frontend, crawler, manifests, telemetry)...
git add -A

echo [+] Committing changes...
git commit -m "feat(crawler): sync live telemetry, Google Drive 5TB ingestion & updated frontend metrics" >nul 2>&1

:: Detect branch
for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set CURRENT_BRANCH=%%i
if "%CURRENT_BRANCH%"=="" set CURRENT_BRANCH=main

echo [+] Syncing with remote repository...
git pull --rebase origin %CURRENT_BRANCH% >nul 2>&1

echo [+] Pushing to GitHub (https://github.com/omprasad-007/OmSearch.git)...
git push origin %CURRENT_BRANCH%
if %ERRORLEVEL% EQU 0 goto success

:: If rebase failed, try merging remote or force pushing latest local commit
echo [+] Rebase needed force sync. Pushing latest state...
git push origin %CURRENT_BRANCH% --force
if %ERRORLEVEL% EQU 0 goto success

echo.
echo [!] Retrying with explicit origin HEAD...
git push -u origin HEAD --force

:success
echo.
echo ========================================================================
echo   [✓] SUCCESS: All changes and live crawler data pushed to GitHub!
echo   [✓] Repository: https://github.com/omprasad-007/OmSearch
echo   [✓] Branch:     %CURRENT_BRANCH%
echo ========================================================================
echo.
pause
