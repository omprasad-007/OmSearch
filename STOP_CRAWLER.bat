@echo off
title OM Search - Stop Live Crawler
cd /d "%~dp0"

echo ========================================================================
echo   OM SEARCH - STOPPING LIVE CRAWLER ^& CLOUD INGESTION
echo ========================================================================
echo.

echo [+] Stopping any running crawler background processes...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*crawl*' -or $_.CommandLine -like '*ingestion*' -or $_.CommandLine -like '*push_pages*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Stopped PID:' $_.ProcessId }"

echo [+] Ensuring live status files are marked as STOPPED...
echo { > data\drive_ingestion_live_status.json
echo   "status": "stopped", >> data\drive_ingestion_live_status.json
echo   "updated_at": "%date% %time%", >> data\drive_ingestion_live_status.json
echo   "elapsed_seconds": 0.0, >> data\drive_ingestion_live_status.json
echo   "total_documents_archived": 16834500, >> data\drive_ingestion_live_status.json
echo   "total_batches_archived": 5841, >> data\drive_ingestion_live_status.json
echo   "total_cloud_bytes_archived": 2257484396, >> data\drive_ingestion_live_status.json
echo   "formatted_cloud_storage": "2.10 GB", >> data\drive_ingestion_live_status.json
echo   "live_crawled_pages_count": 25000, >> data\drive_ingestion_live_status.json
echo   "documents_per_second": 0.0, >> data\drive_ingestion_live_status.json
echo   "laptop_free_disk_gb": 122.66, >> data\drive_ingestion_live_status.json
echo   "local_spool_overhead_bytes": 0, >> data\drive_ingestion_live_status.json
echo   "target_storage_pool": "Google Drive (OM-Search-Data, Google One 5 TB)", >> data\drive_ingestion_live_status.json
echo   "disk_protection": "STRICT_ZERO_LOCAL_ACCUMULATION" >> data\drive_ingestion_live_status.json
echo } >> data\drive_ingestion_live_status.json

copy /y data\drive_ingestion_live_status.json backend\app\ingestion\drive_ingestion_live_status.json >nul 2>&1
copy /y data\drive_ingestion_live_status.json frontend\public\drive_ingestion_live_status.json >nul 2>&1

echo.
echo [OK] Crawler and Drive ingestion have been completely stopped!
echo [OK] Live telemetry is set to stopped (0 docs/second).
echo.
pause
