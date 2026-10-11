import sqlite3

for db_name in ['backend/om_search_fts.db', 'backend/om_search_local.db']:
    try:
        conn = sqlite3.connect(db_name)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cur.fetchall()]
        print(f"=== {db_name} ===")
        for t in tables:
            try:
                cur.execute(f"SELECT count(*) FROM [{t}]")
                cnt = cur.fetchone()[0]
                print(f"  {t}: {cnt}")
            except Exception:
                pass
        conn.close()
    except Exception as e:
        print(f"{db_name}: error {e}")
