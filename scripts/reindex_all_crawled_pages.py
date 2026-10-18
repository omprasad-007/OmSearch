#!/usr/bin/env python3
"""
OM Search — Sync All Crawled Pages into Active Search Index (SQLite FTS5)
Reads all real web pages from frontend/public/crawled_pages.json and data/crawled_batch_live.json
and indexes them directly into backend/om_search_local.db for instantaneous, rich search results.
"""
import os
import sys
import json
import sqlite3
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone

_project_root = Path(__file__).resolve().parent.parent
_backend_dir = _project_root / "backend"
_db_path = _backend_dir / "om_search_local.db"

def main():
    print("=" * 80)
    print("  OM SEARCH — SYNC CRAWLED PAGES INTO ACTIVE SEARCH ENGINE INDEX")
    print("=" * 80)
    print(f"[+] Target Database: {_db_path}")

    # Locate crawled pages JSON
    candidates = [
        _project_root / "frontend" / "public" / "crawled_pages.json",
        _project_root / "data" / "crawled_batch_live.json",
    ]
    
    pages = []
    seen_urls = set()
    for c in candidates:
        if c.exists():
            try:
                with open(c, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        u = item.get("url")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            pages.append(item)
            except Exception as e:
                print(f"[!] Warning reading {c.name}: {e}")

    print(f"[+] Loaded {len(pages):,} unique real-web crawled pages from disk.")
    if not pages:
        print("[!] No crawled pages found.")
        return

    # Connect to SQLite
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path))
    cur = conn.cursor()

    # Ensure schema
    cur.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT UNIQUE,
        url TEXT UNIQUE,
        canonical_url TEXT,
        domain TEXT,
        title TEXT,
        snippet TEXT,
        content TEXT,
        language TEXT DEFAULT 'en',
        document_type TEXT DEFAULT 'webpage',
        published_at TEXT,
        indexed_at TEXT,
        pagerank REAL DEFAULT 0.0
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_domain ON documents(domain);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_title ON documents(title);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_url ON documents(url);")

    # Ensure FTS5 virtual table
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts';")
    if not cur.fetchone():
        cur.execute("""
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            title,
            snippet,
            content,
            content='documents',
            content_rowid='rowid',
            tokenize = 'porter unicode61 remove_diacritics 1'
        );
        """)
        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
          INSERT INTO documents_fts(rowid, title, snippet, content)
          VALUES (new.rowid, new.title, new.snippet, new.content);
        END;
        """)

    # Bulk insert
    print(f"[+] Indexing {len(pages):,} pages into SQLite FTS5 search engine...")
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for p in pages:
        url = p.get("url")
        doc_id = p.get("id") or hashlib.sha256(url.encode()).hexdigest()[:16]
        title = p.get("title") or url
        snippet = p.get("snippet") or ""
        content = p.get("content") or f"{title}\n\n{snippet}"
        domain = p.get("domain") or urlparse(url).netloc.lower()

        try:
            cur.execute("""
            INSERT OR REPLACE INTO documents 
            (id, url, canonical_url, domain, title, snippet, content, language, document_type, published_at, indexed_at, pagerank)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                doc_id,
                url,
                p.get("canonical_url", url),
                domain,
                title,
                snippet,
                content,
                p.get("language", "en"),
                "live_web_page",
                p.get("published_at", "2026-01-01T00:00:00Z"),
                p.get("indexed_at", now_iso),
                float(p.get("pagerank", 0.85))
            ))
            inserted += 1
        except Exception:
            pass

    conn.commit()

    # Rebuild FTS index to ensure 100% sync
    print("[+] Rebuilding full-text search inverted index (FTS5)...")
    try:
        cur.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild');")
        conn.commit()
    except Exception as e:
        print(f"[*] FTS rebuild notice: {e}")

    cur.execute("SELECT COUNT(*) FROM documents;")
    total_docs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT domain) FROM documents;")
    total_domains = cur.fetchone()[0]

    conn.close()

    print("\n" + "=" * 80)
    print("  [✓] SEARCH ENGINE DATABASE SYNCHRONIZED SUCCESSFULLY!")
    print(f"  [✓] Active Searchable Documents: {total_docs:,}")
    print(f"  [✓] Distinct Domains Indexed:    {total_domains:,}")
    print(f"  [✓] Database Size:               {_db_path.stat().st_size / (1024*1024):.2f} MB")
    print("========================================================================\n")

if __name__ == "__main__":
    main()
