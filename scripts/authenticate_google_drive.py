#!/usr/bin/env python3
"""
OM Search — Administrative Google Drive Authentication Tool
Safely authorizes your Google One account without exposing OAuth controls
to public users on the search frontend.
"""
import sys
import time
import webbrowser
import urllib.request
import json
from pathlib import Path

# Add backend to sys.path
_backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from app.services.google_drive_storage import get_google_drive_service


def main():
    print("=" * 70)
    print("OM SEARCH — PRIVATE ADMIN GOOGLE DRIVE AUTHORIZATION")
    print("=" * 70)

    gdrive_svc = get_google_drive_service()
    settings = gdrive_svc.settings

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        print("[!] Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET missing in backend/.env")
        return

    print(f"Using Client ID: {settings.GOOGLE_CLIENT_ID[:25]}...")
    print(f"Redirect URI:   {settings.GOOGLE_REDIRECT_URI}")

    # Generate consent URL
    try:
        # Register state with running backend
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/storage/google-drive/connect",
            headers={"X-Operator-Token": settings.OPERATOR_API_KEY},
            method="POST",
        )
        res = urllib.request.urlopen(req)
        data = json.loads(res.read())
        auth_url = data["authorization_url"]
    except Exception as e:
        # Fallback to direct service generation
        auth_url, _ = gdrive_svc.get_authorization_url()

    print("\n[+] Opening Google Authorization in your default web browser...")
    print("\nIf your browser does not open automatically, copy & paste this link:")
    print("-" * 70)
    print(auth_url)
    print("-" * 70)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("\nWaiting for you to click 'Allow' in the browser window...")
    for i in range(120):  # wait up to 2 minutes
        time.sleep(2)
        try:
            status_res = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/storage/health")
            health_data = json.loads(status_res.read())
            if health_data.get("google_drive", {}).get("connected"):
                email = health_data["google_drive"].get("user_email")
                print(f"\n[✓] SUCCESS: Google Drive connected for account: {email}")
                print("[✓] Your 5 TB Google One storage is now actively linked to OM Search.")
                print("[✓] Durable archives will now stream into 'OM-Search-Data' on Google Drive.")
                return
        except Exception:
            pass
        if i % 5 == 0 and i > 0:
            print(f"    ...still waiting for authorization ({i*2}s)")

    print("\n[!] Timeout waiting for authorization. Please rerun the script when ready.")


if __name__ == "__main__":
    main()
