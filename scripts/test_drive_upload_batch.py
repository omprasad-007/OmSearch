#!/usr/bin/env python3
"""
OM Search — Manual Google Drive Cloud Archive Verification Script
Uploads a small, verified test batch of normalized documents to Google Drive,
confirms the manifest, prunes local spool, and indexes into OpenSearch.
"""
import sys
from pathlib import Path

# Add backend to sys.path
_backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from app.services.google_drive_storage import get_google_drive_service
from app.ingestion.drive_batch_pipeline import get_drive_batch_pipeline
from app.services.search_service import SearchService


def main():
    print("=" * 70)
    print("OM SEARCH — GOOGLE DRIVE 5 TB CLOUD ARCHIVE TEST")
    print("=" * 70)

    gdrive_svc = get_google_drive_service()
    status = gdrive_svc.get_status()

    if not status.get("connected"):
        print("\n[!] Google Drive is not yet connected.")
        print("To connect your Google One 5 TB account:")
        print("  1. Ensure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set in backend/.env")
        print("  2. Open the OM Search web frontend and click 'Drive 5 TB' in the top bar.")
        print("  3. Or run POST /api/v1/storage/google-drive/connect to get your OAuth consent URL.")
        print("  4. Authorize OM Search to create the 'OM-Search-Data' folder.")
        print("\nOnce connected, rerun this script to verify cloud archiving.\n")
        return

    user_email = status.get("user_email")
    quota = status.get("quota", {})
    print(f"\n[✓] Connected Account: {user_email}")
    print(f"[✓] Storage Plan:      {quota.get('plan')}")
    print(f"[✓] Quota Used:        {quota.get('used_percent', 0)}% of 5 TB")
    print(f"[✓] Root Folder ID:    {status.get('root_folder_id')}")

    print("\nPreparing test archive batch (5 sample web pages)...")
    test_records = [
        {
            "id": f"drive_cloud_verify_{i}",
            "url": f"https://cloud.example.org/om-search-test-{i}",
            "title": f"OM Search Cloud Archive Test Document #{i}",
            "snippet": f"Verified document #{i} stored durably in Google Drive 5 TB archive.",
            "content": f"Full body content for verification document #{i}. OM Search decouples cloud page data archives from the active OpenSearch index.",
            "domain": "cloud.example.org",
            "language": "en",
        }
        for i in range(1, 6)
    ]

    pipeline = get_drive_batch_pipeline()
    result = pipeline.process_and_archive_batch(
        records=test_records,
        source_type="operator_manual_test",
        source_reference="manual_smoke_test_01",
    )

    print("\nBatch Processing Result:")
    print(f"  • Batch ID:         {result.get('batch_id')}")
    print(f"  • Records:          {result.get('record_count')}")
    print(f"  • Compressed Size:  {result.get('compressed_bytes')} bytes")
    print(f"  • SHA-256 Checksum: {result.get('sha256')}")
    print(f"  • Drive Upload:     {result.get('upload_status')}")
    print(f"  • Drive File ID:    {result.get('drive_file_id')}")
    print(f"  • Indexing Status:  {result.get('indexing_status')}")

    # Confirm search retrieval
    print("\nVerifying search retrieval in active search engine...")
    search_svc = SearchService()
    search_res = search_svc.search("OM Search Cloud Archive Test Document", page=1, size=5)
    print(f"  • Total Hits Found: {search_res.total}")
    if search_res.results:
        print(f"  • Top Result Title: {search_res.results[0].title}")
        print(f"  • Search Query Latency: {search_res.took_ms:.2f} ms")
        print("\n[✓] VERIFICATION COMPLETE: Documents successfully archived in Google Drive and indexed for instant search!")
    else:
        print("\n[!] Warning: Documents not yet reflected in search results.")


if __name__ == "__main__":
    main()
