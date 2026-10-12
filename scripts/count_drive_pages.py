import sys
from pathlib import Path
from googleapiclient.discovery import build

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.google_drive_storage import GoogleDriveStorageService

def count_drive_pages():
    storage = GoogleDriveStorageService()
    creds = storage.get_credentials()
    if not creds:
        print("ERROR: Google Drive credentials not found.")
        return

    service = build("drive", "v3", credentials=creds)
    
    # 1. Page Records Folder
    page_folder = "1lmsmzeKd9inNwfOFn5ft82r5hRLwtFpt"
    q = f"'{page_folder}' in parents and trashed = false"
    page_files = []
    page_token = None
    
    while True:
        resp = service.files().list(
            q=q,
            spaces='drive',
            fields='nextPageToken, files(id, name, size, createdTime)',
            pageSize=1000,
            pageToken=page_token
        ).execute()
        page_files.extend(resp.get('files', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    total_bytes = sum(int(f.get('size', 0)) for f in page_files)
    
    # 2. Archive Manifests Folder
    manifest_folder = "1HKMvhPOZFWdsd4eHmHbPGmPAnVxU3OGJ"
    q_man = f"'{manifest_folder}' in parents and trashed = false"
    man_files = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q_man,
            spaces='drive',
            fields='nextPageToken, files(id, name, size)',
            pageSize=1000,
            pageToken=page_token
        ).execute()
        man_files.extend(resp.get('files', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    docs_count = len(page_files) * 2500

    print("==================================================")
    print("       OM SEARCH — GOOGLE DRIVE AUDIT             ")
    print("==================================================")
    print(f"Total Batch Files in Drive (page-records): {len(page_files):,} files")
    print(f"Total Manifest Files in Drive:             {len(man_files):,} manifests")
    print(f"Total Cloud Storage Used:                  {total_bytes / (1024 * 1024):.2f} MB ({total_bytes:,} bytes)")
    print(f"Total Indexed Pages in Google Drive:       {docs_count:,} pages")
    print("--------------------------------------------------")

    # Account quota
    about = service.about().get(fields='storageQuota, user').execute()
    user_info = about.get('user', {})
    quota = about.get('storageQuota', {})
    limit = int(quota.get('limit', 0))
    usage = int(quota.get('usage', 0))
    print(f"Google Account:                            {user_info.get('emailAddress')}")
    print(f"Total Plan Capacity:                       {limit / (1024**4):.2f} TB (Google One 5 TB)")
    print(f"Remaining Free Space:                      {(limit - usage) / (1024**4):.4f} TB")
    print("==================================================")

if __name__ == "__main__":
    count_drive_pages()
