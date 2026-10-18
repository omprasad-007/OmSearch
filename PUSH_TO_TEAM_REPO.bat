@echo off
title OM Search - Sync & Deploy to Team Repo (shreyashmane-dev)
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - PUSH TO TEAM REPOSITORY ^& AUTO-DEPLOY ON RENDER
echo   Target 1 (Render Source): https://github.com/shreyashmane-dev/OmSearch.git
echo   Target 2 (Your Fork):     https://github.com/omprasad-007/OmSearch.git
echo ========================================================================
echo.

:: Ensure both remotes are registered
git remote set-url upstream https://github.com/shreyashmane-dev/OmSearch.git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    git remote add upstream https://github.com/shreyashmane-dev/OmSearch.git >nul 2>&1
)
git remote set-url origin https://github.com/omprasad-007/OmSearch.git >nul 2>&1

echo [+] Staging all latest code, crawler files, and telemetry...
git add -A

echo [+] Creating commit...
git commit -m "feat: upgrade search accuracy with exact keyword matching, title boosts, and full index sync"

echo.
echo ========================================================================
echo   [1/2] PUSHING DIRECTLY TO SHREYASHMANE-DEV (RENDER AUTO-DEPLOY)
echo ========================================================================
echo [+] Pulling upstream changes first...
git pull upstream main --no-rebase -X theirs --allow-unrelated-histories --no-edit

echo [+] Pushing all commits to shreyashmane-dev/OmSearch (main)...
git push upstream main
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [✓] SUCCESS: Pushed directly to shreyashmane-dev/OmSearch!
    echo [✓] Render is now automatically building and deploying all commits!
    goto push_fork
)

echo.
echo ========================================================================
echo   [!] DIRECT PUSH TO SHREYASHMANE-DEV REJECTED
echo ========================================================================
echo   If you do not have direct push collaborator access to shreyashmane-dev,
echo   we will push to your repo and give you a 1-click Pull Request link.
echo ========================================================================

:push_fork
echo.
echo ========================================================================
echo   [2/2] SYNCING TO YOUR REPO (omprasad-007/OmSearch)
echo ========================================================================
git pull origin main --no-rebase -X theirs --allow-unrelated-histories --no-edit
git push origin main
if %ERRORLEVEL% EQU 0 (
    echo [✓] Synced cleanly to omprasad-007/OmSearch!
)

echo.
echo ========================================================================
echo   HOW TO MERGE ONTO SHREYASHMANE-DEV & TRIGGER RENDER DEPLOY:
echo ========================================================================
echo   Open this URL in your browser and click "Create Pull Request" -> "Merge":
echo.
echo   https://github.com/shreyashmane-dev/OmSearch/compare/main...omprasad-007:OmSearch:main
echo.
echo   Once merged on GitHub, Render will immediately deploy all 8 commits!
echo ========================================================================
echo.
pause
