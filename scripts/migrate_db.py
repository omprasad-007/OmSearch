import sys
from pathlib import Path
from sqlalchemy import text

# Add backend to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))

from app.repositories.database import get_db_manager, Base


def run_migrations():
    """Apply schema updates to active database (Postgres or SQLite)."""
    db_mgr = get_db_manager()
    engine = db_mgr.engine
    print(f"Applying migrations to database engine: {'sqlite' if db_mgr.is_sqlite else 'postgresql'}")

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        # Check existing columns in urls
        if db_mgr.is_sqlite:
            res = conn.execute(text("PRAGMA table_info(urls)"))
            existing_cols = {row[1] for row in res.fetchall()}
            
            columns_to_add = [
                ("normalized_url", "TEXT"),
                ("scheme", "VARCHAR(10) DEFAULT 'https'"),
                ("discovery_source", "TEXT"),
                ("depth", "INTEGER DEFAULT 0"),
                ("priority", "INTEGER DEFAULT 0"),
                ("attempt_count", "INTEGER DEFAULT 0"),
                ("next_fetch_at", "DATETIME"),
                ("last_error", "TEXT"),
                ("worker_id", "VARCHAR(64)"),
                ("lease_expires_at", "DATETIME"),
            ]
            for col_name, col_type in columns_to_add:
                if col_name not in existing_cols:
                    print(f"Adding column '{col_name}' to 'urls' table...")
                    conn.execute(text(f"ALTER TABLE urls ADD COLUMN {col_name} {col_type}"))

            # Check crawl_jobs columns
            res_jobs = conn.execute(text("PRAGMA table_info(crawl_jobs)"))
            jobs_cols = {row[1] for row in res_jobs.fetchall()}
            if "config" not in jobs_cols:
                conn.execute(text("ALTER TABLE crawl_jobs ADD COLUMN config TEXT"))
            if "indexed_urls" not in jobs_cols:
                conn.execute(text("ALTER TABLE crawl_jobs ADD COLUMN indexed_urls INTEGER DEFAULT 0"))

        else:
            # PostgreSQL column check & alter
            conn.execute(text("""
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS normalized_url TEXT;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS scheme VARCHAR(10) DEFAULT 'https';
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS discovery_source TEXT;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS depth INTEGER DEFAULT 0;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS next_fetch_at TIMESTAMPTZ;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS last_error TEXT;
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64);
                ALTER TABLE urls ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
                ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS config TEXT;
                ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS indexed_urls INTEGER DEFAULT 0;
            """))

        conn.commit()
    print("Database migration completed successfully.")


if __name__ == "__main__":
    run_migrations()
