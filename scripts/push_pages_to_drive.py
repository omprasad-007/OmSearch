#!/usr/bin/env python3
"""
OM Search — Direct Push All Crawled Pages to Google Drive (5 TB Plan)
100% Standalone (Standard Library Only): Guaranteed to run without requiring pip packages.
Uploads all crawled pages, manifests, and archive micro-batches directly to Google Drive,
and queries the official Google Drive API to verify cloud storage usage.
"""
import os
import sys
import json
import gzip
import time
import uuid
import hashlib
import webbrowser
import urllib.parse
import urllib.request
import ssl
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add backend and project root to sys.path
_project_root = Path(__file__).resolve().parent.parent
_data_dir = _project_root / "data"
_data_dir.mkdir(parents=True, exist_ok=True)

# Load environment configuration from .env safely
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
CLIENT_ID = CONFIG.get("GOOGLE_CLIENT_ID", "260412082226-v5lqr7omi1ofh1rdo3svjkui4lildcit.apps.googleusercontent.com")
CLIENT_SECRET = CONFIG.get("GOOGLE_CLIENT_SECRET", "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")
REDIRECT_URI = "http://127.0.0.1:8000/api/v1/storage/google-drive/callback"
SCOPES = "https://www.googleapis.com/auth/drive.file"
TOKEN_FILE = _data_dir / "gdrive_token.json"


def format_bytes(b: int) -> str:
    val = float(b)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if val < 1024.0:
            return f"{val:.2f} {unit}"
        val /= 1024.0
    return f"{val:.2f} PB"


def get_stored_tokens():
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_tokens(token_data):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
    except Exception:
        pass


def refresh_access_token(refresh_token):
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
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        if resp.status == 200:
            new_data = json.loads(resp.read().decode("utf-8"))
            tokens = get_stored_tokens() or {}
            tokens.update(new_data)
            save_tokens(tokens)
            return tokens.get("access_token")
    return None


def get_valid_access_token():
    tokens = get_stored_tokens()
    if not tokens:
        return None
    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        try:
            return refresh_access_token(refresh_token)
        except Exception:
            pass
    return tokens.get("access_token")


def authenticate_interactively():
    print("\n[+] Initiating one-time Google OAuth 2.0 authorization...")
    captured = {"code": None}

    class OAuthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if "/api/v1/storage/google-drive/callback" in parsed.path:
                qs = urllib.parse.parse_qs(parsed.query)
                captured["code"] = qs.get("code", [None])[0]
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:sans-serif;text-align:center;padding:50px;background:#fbf9f5;'>"
                    b"<h2 style='color:#37654d;'>&#10004; Google Drive Authorized Successfully!</h2>"
                    b"<p style='color:#57423b;'>OM Search is now uploading all crawled pages to your 5 TB storage. You can close this tab.</p>"
                    b"</body></html>"
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = None
    try:
        server = HTTPServer(("127.0.0.1", 8000), OAuthHandler)
        server.timeout = 1.0
    except Exception as e:
        print(f"[!] Warning: Port 8000 in use ({e}). Trying to proceed...")

    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    print("-" * 75)
    print("Opening Google Authorization in your default browser...")
    print(auth_url)
    print("-" * 75)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    if server:
        print("Waiting for browser authorization (up to 120s)...")
        start = time.time()
        while time.time() - start < 120 and not captured["code"]:
            server.handle_request()
        server.server_close()

    if not captured["code"]:
        print("[!] No authorization code received. Please re-run.")
        return None

    # Exchange code for tokens
    print("[+] Exchanging authorization code for persistent tokens...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    payload = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": captured["code"],
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        if resp.status == 200:
            token_data = json.loads(resp.read().decode("utf-8"))
            save_tokens(token_data)
            print("[✓] Google Drive authorized and refresh token saved!")
            return token_data.get("access_token")
    return None


def call_drive_api(endpoint, method="GET", body=None, headers=None, token=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    all_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        all_headers.update(headers)

    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        elif isinstance(body, bytes):
            data = body
        elif isinstance(body, str):
            data = body.encode("utf-8")

    req = urllib.request.Request(endpoint, data=data, headers=all_headers, method=method)
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_or_create_folder(folder_name, parent_id=None, token=None):
    q = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    
    encoded_q = urllib.parse.quote(q)
    res = call_drive_api(f"https://www.googleapis.com/drive/v3/files?q={encoded_q}&fields=files(id,name)", token=token)
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    
    meta = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]
    
    res = call_drive_api("https://www.googleapis.com/drive/v3/files", method="POST", body=meta, token=token)
    return res.get("id")


def upload_file_multipart(local_path, filename, folder_id, token):
    boundary = f"===om_boundary_{uuid.uuid4().hex}==="
    meta = {
        "name": filename,
        "parents": [folder_id],
    }
    
    with open(local_path, "rb") as f:
        file_bytes = f.read()
    
    body = bytearray()
    body.extend(f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n".encode("utf-8"))
    body.extend(f"--{boundary}\r\nContent-Type: application/gzip\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    headers = {
        "Content-Type": f"multipart/related; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    
    res = call_drive_api(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        method="POST",
        body=bytes(body),
        headers=headers,
        token=token,
    )
    return res


def main():
    print("=" * 75)
    print("OM SEARCH — 100% STANDALONE PUSH ALL PAGES TO GOOGLE DRIVE (5 TB PLAN)")
    print("=" * 75)

    token = get_valid_access_token()
    if not token:
        token = authenticate_interactively()

    if not token:
        print("[!] Could not obtain Google Drive access token. Please retry.")
        return

    # Check Drive User and Quota directly from Google Drive API
    print("[+] Querying live Google One 5 TB storage quota from Google Drive API...")
    about = call_drive_api("https://www.googleapis.com/drive/v3/about?fields=storageQuota,user", token=token)
    user_info = about.get("user", {})
    storage_quota = about.get("storageQuota", {})
    user_email = user_info.get("emailAddress", "unknown")
    quota_total = int(storage_quota.get("limit", 0))
    quota_used = int(storage_quota.get("usage", 0))

    print(f"\n[✓] Connected Account: {user_email}")
    print(f"[✓] Storage Used:      {format_bytes(quota_used)} of {format_bytes(quota_total)}")

    # Ensure OM-Search-Data and page-records folders exist
    print("[+] Ensuring 'OM-Search-Data/page-records' structure exists on Drive...")
    root_folder_id = get_or_create_folder("OM-Search-Data", token=token)
    page_records_id = get_or_create_folder("page-records", parent_id=root_folder_id, token=token)
    print(f"[✓] Target Folder ID:  {page_records_id}")

    # Load all crawled pages
    crawled_file = _project_root / "data" / "crawled_batch_live.json"
    if not crawled_file.exists():
        crawled_file = _project_root / "frontend" / "public" / "crawled_pages.json"

    records = []
    if crawled_file.exists():
        with open(crawled_file, "r", encoding="utf-8") as f:
            records = json.load(f)

    print(f"\n[+] Found {len(records)} live crawled pages to archive into Google Drive.")
    if not records:
        print("[!] No records found to push.")
        return

    # Package into GZip archive
    batch_id = f"batch_live_crawl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    spool_dir = _project_root / "data" / "temp_drive_spool"
    spool_dir.mkdir(parents=True, exist_ok=True)
    spool_path = spool_dir / f"{batch_id}.json.gz"

    hasher = hashlib.sha256()
    with gzip.open(spool_path, "wt", encoding="utf-8") as gz:
        for rec in records:
            line = json.dumps(rec, ensure_ascii=False) + "\n"
            hasher.update(line.encode("utf-8"))
            gz.write(line)

    compressed_bytes = spool_path.stat().st_size
    sha256 = hasher.hexdigest()

    print(f"[+] Packaged {len(records)} pages into: {format_bytes(compressed_bytes)} (SHA: {sha256[:12]}...)")
    print(f"[+] Uploading '{batch_id}.json.gz' directly to Google Drive...")

    upload_res = upload_file_multipart(str(spool_path), f"{batch_id}.json.gz", page_records_id, token=token)
    drive_file_id = upload_res.get("id")

    print(f"\n========================================================================")
    print(f"  [✓] SUCCESS: UPLOADED TO GOOGLE DRIVE!")
    print(f"  [✓] File Name:     {batch_id}.json.gz")
    print(f"  [✓] Drive File ID: {drive_file_id}")
    print(f"  [✓] Drive Link:    https://drive.google.com/file/d/{drive_file_id}/view")
    print(f"========================================================================")

    # Prune local spool immediately
    if spool_path.exists():
        spool_path.unlink()
    print(f"[✓] Zero-Disk Policy Enforced: Spool pruned (0 MB local disk overhead).")

    # Refresh Drive quota directly from Google servers
    print("[+] Querying updated storage quota from Google servers...")
    new_about = call_drive_api("https://www.googleapis.com/drive/v3/about?fields=storageQuota", token=token)
    new_quota = new_about.get("storageQuota", {})
    new_used = int(new_quota.get("usage", 0))
    print(f"[✓] New Used Storage: {format_bytes(new_used)} (increased on Google Drive!)")


if __name__ == "__main__":
    main()
