import sqlite3

db_paths = [
    "backend/om_search_fts.db",
    "om_search_fts.db",
    "om_search_local.db",
    "backend/om_search_local.db"
]

for p in db_paths:
    try:
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        
        # Check if documents table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents';")
        if not cur.fetchone():
            conn.close()
            continue
            
        cur.execute("SELECT COUNT(*) FROM documents;")
        total_before = cur.fetchone()[0]
        
        # Delete fake synthetic guide/daily/articles URLs
        cur.execute("""
        DELETE FROM documents 
        WHERE document_type != 'live_web_page'
           OR url LIKE '%/guide/%'
           OR url LIKE '%/daily/v%'
           OR url LIKE '%/articles/v%'
           OR url LIKE '%/daily-%';
        """)
        deleted_count = cur.rowcount
        
        # Clean FTS table if it exists
        try:
            cur.execute("DELETE FROM documents_fts WHERE rowid NOT IN (SELECT rowid FROM documents);")
        except Exception:
            pass
            
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM documents;")
        total_after = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT domain) FROM documents;")
        domains_after = cur.fetchone()[0]
        
        print(f"[{p}] Purged {deleted_count} fake URLs. Remaining: {total_after} genuine live pages across {domains_after} domains.")
        conn.close()
    except Exception as e:
        print(f"Notice on {p}: {e}")
