#!/usr/bin/env python3
"""
OM Search — Google Drive Storage Diagnostic & Live Verification Tool
Directly checks token validity, queries Google's server quota, lists all files
in OM-Search-Data, performs a test upload, and reports exact storage numbers.
"""
import os
import sys
import json
import gzip
import time
import uuid
import ssl
import urllib.request
import urllib.parse
import webbrowser
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
_data_dir = _project_root / "data"
TOKEN_FILE = _data_dir / "gdrive_token.json"

def format_bytes(b: int) -> str:
    val = float(b)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if val < 1024.0:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"

def load_env_vars():
    env_file = _project_root / ".env"
    env_data = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_data[k.strip()] = v.strip().strip("'").strip('"')
    return env_data

CONFIG = load_env_vars()
CLIENT_ID = CONFIG.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = CONFIG.get("GOOGLE_CLIENT_SECRET", "")

def get_token():
    if not TOKEN_FILE.exists():
        print("[!] No gdrive_token.json found in data/ folder.")
        return None
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return tokens.get("access_token")
    
    # Always refresh to ensure fresh access
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    payload = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            if resp.status == 200:
                new_data = json.loads(resp.read().decode("utf-8"))
                tokens.update(new_data)
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(tokens, f, indent=2)
                return tokens.get("access_token")
    except Exception as e:
        print(f"[!] Token refresh error: {e}")
        return tokens.get("access_token")

def call_api(url, method="GET", body=None, headers=None, token=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    all_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        all_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=all_headers, method=method)
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("=" * 80)
    print("  OM SEARCH — GOOGLE DRIVE CONNECTION & STORAGE VERIFICATION")
    print("=" * 80)
    
    token = get_token()
    if not token:
        print("[!] Could not obtain Google Drive access token. Please run PUSH_ALL_TO_DRIVE.bat")
        return
    
    print("[+] Querying Google Account & Storage Quota from Google servers...")
    try:
        about = call_api("https://www.googleapis.com/drive/v3/about?fields=storageQuota,user", token=token)
    except Exception as e:
        print(f"[!] Failed to query Google Drive about endpoint: {e}")
        return
    
    user = about.get("user", {})
    quota = about.get("storageQuota", {})
    email = user.get("emailAddress", "unknown")
    used_bytes = int(quota.get("usage", 0))
    limit_bytes = int(quota.get("limit", 0))
    
    print(f"\n[✓] Connected Google Account: {email}")
    print(f"[✓] Google Drive Storage Used: {format_bytes(used_bytes)} ({used_bytes:,} bytes)")
    print(f"[✓] Google Drive Plan Total:   {format_bytes(limit_bytes)} ({limit_bytes:,} bytes)")
    
    # Check folder OM-Search-Data
    print("\n[+] Inspecting 'OM-Search-Data' folder on Google Drive...")
    q = urllib.parse.quote("name = 'OM-Search-Data' and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    res = call_api(f"https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id,name)", token=token)
    folders = res.get("files", [])
    if not folders:
        print("[*] 'OM-Search-Data' folder does not exist yet. Creating it now...")
        meta = json.dumps({"name": "OM-Search-Data", "mimeType": "application/vnd.google-apps.folder"}).encode("utf-8")
        folder_res = call_api("https://www.googleapis.com/drive/v3/files", method="POST", body=meta, headers={"Content-Type": "application/json"}, token=token)
        root_folder_id = folder_res.get("id")
        print(f"[✓] Created root folder 'OM-Search-Data' (ID: {root_folder_id})")
    else:
        root_folder_id = folders[0]["id"]
        print(f"[✓] Found root folder 'OM-Search-Data' (ID: {root_folder_id})")
        
    # Check page-records subfolder
    q_sub = urllib.parse.quote(f"name = 'page-records' and '{root_folder_id}' in parents and trashed = false")
    res_sub = call_api(f"https://www.googleapis.com/drive/v3/files?q={q_sub}&fields=files(id,name)", token=token)
    sub_folders = res_sub.get("files", [])
    if not sub_folders:
        meta_sub = json.dumps({"name": "page-records", "mimeType": "application/vnd.google-apps.folder", "parents": [root_folder_id]}).encode("utf-8")
        sub_res = call_api("https://www.googleapis.com/drive/v3/files", method="POST", body=meta_sub, headers={"Content-Type": "application/json"}, token=token)
        page_records_id = sub_res.get("id")
        print(f"[✓] Created subfolder 'page-records' (ID: {page_records_id})")
    else:
        page_records_id = sub_folders[0]["id"]
        print(f"[✓] Found subfolder 'page-records' (ID: {page_records_id})")
        
    # List files in page-records
    q_files = urllib.parse.quote(f"'{page_records_id}' in parents and trashed = false")
    file_list = call_api(f"https://www.googleapis.com/drive/v3/files?q={q_files}&fields=files(id,name,size,createdTime)&pageSize=100", token=token)
    files = file_list.get("files", [])
    total_folder_bytes = sum(int(f.get("size", 0)) for f in files)
    
    print(f"\n[+] Total Archived Batches in Google Drive: {len(files)} files ({format_bytes(total_folder_bytes)})")
    for f in files[:10]:
        sz = format_bytes(int(f.get("size", 0)))
        print(f"  - {f.get('name')} ({sz}) -> ID: {f.get('id')}")
    if len(files) > 10:
        print(f"  ... and {len(files) - 10} more files.")
        
    # Perform a test upload to verify direct multipart writing
    print("\n[+] Testing live upload of verified micro-batch to Google Drive...")
    test_filename = f"verify_test_{int(time.time())}.json.gz"
    test_content = json.dumps({
        "test": True,
        "service": "OM Search",
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "description": "Verified cloud ingestion test micro-batch"
    }).encode("utf-8")
    gz_bytes = gzip.compress(test_content)
    
    boundary = f"om_boundary_{uuid.uuid4().hex}"
    meta = json.dumps({"name": test_filename, "parents": [page_records_id]}).encode("utf-8")
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
    body.extend(meta)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b"Content-Type: application/gzip\r\n\r\n")
    body.extend(gz_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    try:
        upload_res = call_api(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            method="POST",
            body=bytes(body),
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            token=token,
        )
        test_file_id = upload_res.get("id")
        print(f"\n========================================================================")
        print(f"  [✓] LIVE GOOGLE DRIVE UPLOAD CONFIRMED SUCCESSFUL!")
        print(f"  [✓] Uploaded File: {test_filename}")
        print(f"  [✓] Drive File ID: {test_file_id}")
        print(f"  [✓] Direct Link:   https://drive.google.com/file/d/{test_file_id}/view")
        print(f"========================================================================")
    except Exception as e:
        print(f"[!] Upload test failed: {e}")
        
    folder_url = f"https://drive.google.com/drive/folders/{root_folder_id}"
    print(f"\n[+] Opening 'OM-Search-Data' folder in your default browser: {folder_url}")
    try:
        webbrowser.open(folder_url)
    except Exception:
        pass

if __name__ == "__main__":
    main()
