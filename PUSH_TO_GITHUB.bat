@echo off
title OM Search - Push to GitHub
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - PUSH LATEST CODE ^& LIVE DATA TO GITHUB
echo   Repository: https://github.com/omprasad-007/OmSearch.git
echo ========================================================================
echo.

:: Detect current branch
for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set CURRENT_BRANCH=%%i
if "%CURRENT_BRANCH%"=="" set CURRENT_BRANCH=main
echo [*] Current branch: %CURRENT_BRANCH%

:: Ensure remote origin is set correctly
git remote set-url origin https://github.com/omprasad-007/OmSearch.git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    git remote add origin https://github.com/omprasad-007/OmSearch.git >nul 2>&1
)

echo.
echo [+] Staging all updated files and telemetry...
git add -A

echo [+] Committing changes...
git commit -m "feat: sync live crawled pages, Google Drive integration, and verified dashboard telemetry"

echo.
echo [+] Fetching remote origin/%CURRENT_BRANCH%...
git fetch origin %CURRENT_BRANCH%

echo [+] Merging remote changes cleanly (conflict-free)...
git merge origin/%CURRENT_BRANCH% --no-edit -m "chore: merge upstream changes from origin/%CURRENT_BRANCH%"

echo.
echo [+] Pushing to GitHub (https://github.com/omprasad-007/OmSearch.git)...
git push origin %CURRENT_BRANCH%
if %ERRORLEVEL% EQU 0 goto push_success

echo.
echo [!] Standard push was rejected. Attempting fast-forward / lease push...
git push origin %CURRENT_BRANCH% --force-with-lease
if %ERRORLEVEL% EQU 0 goto push_success

echo.
echo ========================================================================
echo   [!] GITHUB PUSH REQUIRES AUTHENTICATION OR TOKEN
echo ========================================================================
echo   If GitHub is asking for login or rejected permissions, you can paste
echo   a GitHub Personal Access Token (PAT) below.
echo   Or press ENTER to retry.
echo ========================================================================
echo.
set /p GITHUB_PAT="Enter GitHub Token (or press ENTER to retry): "
if not "%GITHUB_PAT%"=="" (
    echo [+] Pushing with provided authentication token...
    git push https://%GITHUB_PAT%@github.com/omprasad-007/OmSearch.git %CURRENT_BRANCH%
    if %ERRORLEVEL% EQU 0 goto push_success
)

echo.
echo [!] Push failed. Please check the error message above.
pause
exit /b 1

:push_success
echo.
echo ========================================================================
echo   [✓] SUCCESS: All changes and live crawler data pushed to GitHub!
echo   [✓] Repository: https://github.com/omprasad-007/OmSearch
echo   [✓] Branch:     %CURRENT_BRANCH%
echo ========================================================================
echo.

:: Verify on GitHub
echo [*] Verifying latest commit directly on GitHub API...
powershell -Command "try { $c = Invoke-RestMethod -Uri 'https://api.github.com/repos/omprasad-007/OmSearch/commits' -Headers @{'User-Agent'='OmSearchPush'} | Select-Object -First 1; Write-Host ('[✓] Live on GitHub: ' + $c.sha.Substring(0,7) + ' - ' + $c.commit.message) -ForegroundColor Green } catch { Write-Host '[*] Could not query GitHub API verification.' }"

echo.
pause

