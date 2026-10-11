import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Generator
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import get_settings

logger = logging.getLogger(__name__)
Base = declarative_base()


class FrontierStatus:
    DISCOVERED = "DISCOVERED"
    QUEUED = "QUEUED"
    FETCHING = "FETCHING"
    FETCHED = "FETCHED"
    SKIPPED_POLICY = "SKIPPED_POLICY"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DUPLICATE = "DUPLICATE"


class URLRecord(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False, unique=True)
    normalized_url = Column(Text, nullable=True, index=True)
    canonical_url = Column(Text, nullable=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    scheme = Column(String(10), default="https")
    discovery_source = Column(Text, nullable=True)  # Parent / referrer URL
    depth = Column(Integer, default=0, index=True)
    status = Column(String(50), default=FrontierStatus.DISCOVERED, index=True)
    priority = Column(Integer, default=0, index=True)
    attempt_count = Column(Integer, default=0)
    next_fetch_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    http_status = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    worker_id = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(50), nullable=False)  # seed_ingest, manual, crawler, continuous
    status = Column(String(50), default="pending", index=True)  # pending, running, paused, completed, cancelled, failed
    config = Column(Text, nullable=True)  # JSON-encoded job parameters
    total_urls = Column(Integer, default=0)
    processed_urls = Column(Integer, default=0)
    indexed_urls = Column(Integer, default=0)
    failed_urls = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)


class DocumentLifecycle(Base):
    __tablename__ = "document_lifecycle"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_id = Column(Integer, ForeignKey("urls.id", ondelete="CASCADE"), nullable=True)
    canonical_url = Column(Text, nullable=False)
    action = Column(String(50), nullable=False)  # discovered, queued, fetched, parsed, deduplicated, indexed, skipped, error
    status = Column(String(50), nullable=False)  # success, warning, failure
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PageLink(Base):
    __tablename__ = "page_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_url = Column(Text, nullable=False, index=True)
    target_url = Column(Text, nullable=False, index=True)
    source_domain = Column(String(255), nullable=True, index=True)
    target_domain = Column(String(255), nullable=True, index=True)
    anchor_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PageAuthority(Base):
    __tablename__ = "page_authority"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False, unique=True, index=True)
    canonical_url = Column(Text, nullable=True, index=True)
    domain = Column(String(255), nullable=True, index=True)
    pagerank = Column(Float, default=0.0, index=True)
    in_degree = Column(Integer, default=0)
    out_degree = Column(Integer, default=0)
    snapshot_version = Column(String(50), default="v1")
    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SourceType:
    LIVE_CRAWLER = "live_crawler"
    ARCHIVE_IMPORTER = "archive_importer"
    OPERATOR_SEED = "operator_seed"


class TaskPriorityClass:
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"
    BULK_ARCHIVE = "BULK_ARCHIVE"
    RETRY = "RETRY"


class TaskStatus:
    PENDING = "PENDING"
    LEASED = "LEASED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class DocumentRegistry(Base):
    """
    Authoritative document registry.
    Maintains the relationship between canonical document identity,
    active searchable representation, and content fingerprint.
    """
    __tablename__ = "document_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(64), unique=True, nullable=False, index=True)
    canonical_url = Column(Text, nullable=False, index=True)
    primary_url = Column(Text, nullable=False)
    domain = Column(String(255), nullable=False, index=True)
    current_content_hash = Column(String(64), nullable=True, index=True)
    active_source_type = Column(String(50), nullable=False, default=SourceType.LIVE_CRAWLER)
    active_capture_id = Column(String(64), nullable=True, index=True)
    source_captured_at = Column(DateTime(timezone=True), nullable=True)
    live_fetched_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    version_sequence = Column(Integer, default=1)
    quality_score = Column(Float, default=1.0)
    reconciliation_status = Column(String(50), default="synced", index=True)  # synced, pending_index, conflict, failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DocumentAlias(Base):
    """
    Alternate URLs (redirects, aliases, mirror links) associated with a canonical document.
    Preserves provenance without polluting search results with duplicate documents.
    """
    __tablename__ = "document_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(64), nullable=False, index=True)
    alternate_url = Column(Text, nullable=False, unique=True, index=True)
    alias_type = Column(String(50), default="canonical_link")  # canonical_link, redirect_301, mirror
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class HistoricalCapture(Base):
    """
    Immutable capture record representing a specific historical snapshot of a URL.
    Preserves historical provenance separately from current searchable state.
    """
    __tablename__ = "historical_captures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capture_id = Column(String(64), unique=True, nullable=False, index=True)
    url_id = Column(Integer, ForeignKey("urls.id", ondelete="CASCADE"), nullable=True)
    url = Column(Text, nullable=False, index=True)
    canonical_url = Column(Text, nullable=False, index=True)
    source_type = Column(String(50), nullable=False, index=True)  # live_crawler, archive_importer
    source_archive_id = Column(String(255), nullable=True, index=True)  # Manifest, WARC, partition ID
    source_captured_at = Column(DateTime(timezone=True), nullable=True, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    title = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    http_status = Column(Integer, default=200)
    headers_json = Column(Text, nullable=True)
    is_searchable_current = Column(Integer, default=0, index=True)  # 1 if active in search index
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IngestionTask(Base):
    """
    Durable unit of work in the unified scheduler.
    Supports atomic leases, priority classes, queue aging, and crash-resilient retries.
    """
    __tablename__ = "ingestion_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    source_type = Column(String(50), nullable=False, index=True)  # live_crawler, archive_importer, urgent_recovery
    work_unit_id = Column(String(255), nullable=False, index=True)  # URL or partition identifier
    priority_class = Column(String(30), nullable=False, default=TaskPriorityClass.ROUTINE, index=True)
    priority_score = Column(Float, default=0.0, index=True)
    estimated_cost = Column(Float, default=1.0)
    status = Column(String(30), nullable=False, default=TaskStatus.PENDING, index=True)
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    lease_owner = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    next_eligible_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    payload_json = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DriveUploadBatch(Base):
    """
    Durable record of a compressed page-data batch uploaded to Google Drive.
    Eliminates reliance on ephemeral/local disk storage for long-term archives.
    """
    __tablename__ = "drive_upload_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(64), unique=True, nullable=False, index=True)
    schema_version = Column(String(20), default="v1")
    source_type = Column(String(50), nullable=False, index=True)  # live_crawler, archive_importer, unified_stream
    source_reference = Column(Text, nullable=True)  # partition, crawl_id range, seed tag
    record_count = Column(Integer, default=0)
    uncompressed_bytes = Column(Integer, default=0)
    compressed_bytes = Column(Integer, default=0)
    sha256_checksum = Column(String(64), nullable=False)
    drive_file_id = Column(String(128), nullable=True, index=True)
    drive_folder_id = Column(String(128), nullable=True)
    drive_file_name = Column(String(255), nullable=False)
    upload_status = Column(String(50), default="pending", index=True)  # pending, uploading, uploaded, verified, failed
    indexing_status = Column(String(50), default="pending", index=True)  # pending, indexed, failed, skipped
    local_spool_path = Column(Text, nullable=True)
    attempt_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DriveOAuthCredential(Base):
    """
    Secure storage for user Google Drive OAuth credentials.
    Supports offline access, automated token refresh, and safe disconnect.
    """
    __tablename__ = "drive_oauth_credentials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(255), nullable=True)
    encrypted_tokens = Column(Text, nullable=False)  # Encrypted OAuth tokens (refresh_token, client_id, etc.)
    root_folder_id = Column(String(128), nullable=True)
    subfolder_ids_json = Column(Text, nullable=True)  # JSON mapping of subfolders
    is_active = Column(Integer, default=1, index=True)
    storage_quota_total_bytes = Column(Integer, nullable=True)
    storage_quota_used_bytes = Column(Integer, nullable=True)
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DriveStorageReport(Base):
    """
    Durable storage audit and reconciliation reports.
    """
    __tablename__ = "drive_storage_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), unique=True, nullable=False, index=True)
    report_type = Column(String(50), default="audit")  # audit, reconcile, quota_check
    summary_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DatabaseManager:
    def __init__(self):
        self.settings = get_settings()
        self._engine = None
        self._sessionmaker = None
        self._is_sqlite = False
        self._initialize_engine()

    def _initialize_engine(self):
        db_url = self.settings.DATABASE_URL
        import socket
        from urllib.parse import urlparse

        # Quick socket check to prevent multi-second psycopg2 connection timeout
        parsed = urlparse(db_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        can_connect = False
        try:
            with socket.create_connection((host, port), timeout=0.1):
                can_connect = True
        except Exception:
            can_connect = False

        if can_connect:
            try:
                engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self._engine = engine
                self._is_sqlite = False
                logger.info("Connected to PostgreSQL database at %s", db_url.split("@")[-1])
            except Exception as e:
                can_connect = False

        if not can_connect:
            if self.settings.USE_SQLITE_FALLBACK_IF_UNAVAILABLE:
                logger.info("PostgreSQL unavailable at %s:%s. Instantly using local SQLite database.", host, port)
                sqlite_url = self.settings.SQLITE_FALLBACK_URL
                if sqlite_url.startswith("sqlite:///./"):
                    from pathlib import Path
                    rel_name = sqlite_url.replace("sqlite:///./", "")
                    backend_dir = Path(__file__).resolve().parents[2]
                    target_db = backend_dir / rel_name
                    sqlite_url = f"sqlite:///{target_db.as_posix()}"

                self._engine = create_engine(
                    sqlite_url,
                    connect_args={"check_same_thread": False},
                )
                self._is_sqlite = True
            else:
                logger.error("Database connection failed for PostgreSQL")
                raise ConnectionError("PostgreSQL unreachable")

        self._sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)
        # Ensure all declared tables exist
        Base.metadata.create_all(bind=self._engine)

    @property
    def is_sqlite(self) -> bool:
        return self._is_sqlite

    @property
    def engine(self):
        return self._engine

    def get_session(self) -> Session:
        if self._sessionmaker is None:
            self._initialize_engine()
        return self._sessionmaker()

    def check_health(self) -> Dict[str, Any]:
        """Check database ping and return health metrics."""
        start_t = time.perf_counter()
        try:
            if self._engine is None:
                self._initialize_engine()
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            latency = (time.perf_counter() - start_t) * 1000
            db_type = "sqlite" if self._is_sqlite else "postgresql"
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "details": {
                    "engine": db_type,
                    "connected": True,
                },
            }
        except Exception as e:
            return {
                "status": "unreachable",
                "latency_ms": None,
                "details": {"error": str(e)},
            }


_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_db() -> Generator[Session, None, None]:
    db = get_db_manager().get_session()
    try:
        yield db
    finally:
        db.close()
