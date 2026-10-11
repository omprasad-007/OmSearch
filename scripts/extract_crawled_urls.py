import json
from pathlib import Path
from urllib.parse import urlparse

log_path = Path("data/drive_continuous_ingestion.log")
urls = set()

if log_path.exists():
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "HTTP Request: GET " in line and "200 OK" in line:
                try:
                    u = line.split("HTTP Request: GET ")[1].split(' "HTTP')[0].strip()
                    if u.startswith("http"):
                        urls.add(u)
                except Exception:
                    pass

print(f"Total unique 200 OK crawled URLs extracted: {len(urls)}")
with open("data/crawled_urls_unique.json", "w", encoding="utf-8") as out:
    json.dump(list(urls), out, indent=2)
