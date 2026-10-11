import pytest
from datetime import datetime, timezone, timedelta
from app.repositories.database import (
    get_db_manager,
    DocumentRegistry,
    HistoricalCapture,
    DocumentAlias,
    SourceType,
)
from app.ingestion.identity_service import DocumentIdentityService, VersionDecision


@pytest.fixture
def identity_service():
    return DocumentIdentityService()


def test_url_canonicalization_and_fingerprints(identity_service):
    raw_url = "https://example.com/test?utm_source=twitter&b=2&a=1#section"
    content = "Unified Ingestion Architecture for OM Search Engine."

    identities = identity_service.resolve_identities(raw_url, content)
    assert "utm_source" not in identities["canonical_url"]
    assert "a=1&b=2" in identities["canonical_url"]
    assert "#section" not in identities["canonical_url"]
    assert identities["domain"] == "example.com"
    assert len(identities["doc_id"]) >= 24
    assert len(identities["content_hash"]) == 64


def test_archive_cannot_overwrite_newer_live_document(identity_service):
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(days=30)
    url = f"https://example.com/breaking-news-{int(now.timestamp())}"

    # 1. First ingested via live crawler
    live_content = "Today's live news updates from the web."
    live_ids = identity_service.resolve_identities(url, live_content)

    decision_live, cap_live = identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=live_ids["canonical_url"],
        doc_id=live_ids["doc_id"],
        domain=live_ids["domain"],
        title="Breaking News Live Edition",
        snippet="Live news snippet",
        content=live_content,
        content_hash=live_ids["content_hash"],
        source_type=SourceType.LIVE_CRAWLER,
        live_fetched_at=now,
    )
    assert decision_live.action == "update_searchable"
    assert decision_live.is_searchable is True

    # 2. Later, bulk importer encounters historical snapshot from 30 days ago
    archive_content = "Last month's historical news snapshot from archive."
    archive_ids = identity_service.resolve_identities(url, archive_content)

    decision_archive, cap_archive = identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=archive_ids["canonical_url"],
        doc_id=archive_ids["doc_id"],
        domain=archive_ids["domain"],
        title="Breaking News Archive Old Edition",
        snippet="Archive snippet",
        content=archive_content,
        content_hash=archive_ids["content_hash"],
        source_type=SourceType.ARCHIVE_IMPORTER,
        source_archive_id="warc_batch_001",
        source_captured_at=earlier,
    )

    # Policy MUST reject overwriting the searchable live version
    assert decision_archive.action == "archive_capture_only"
    assert decision_archive.is_searchable is False

    # Check DB state
    db = get_db_manager().get_session()
    try:
        reg = db.query(DocumentRegistry).filter_by(doc_id=live_ids["doc_id"]).first()
        assert reg.active_source_type == SourceType.LIVE_CRAWLER

        # Historical capture is recorded and preserved
        caps = db.query(HistoricalCapture).filter_by(canonical_url=live_ids["canonical_url"]).all()
        assert len(caps) >= 2
    finally:
        db.close()


def test_live_crawl_updates_older_archive_document(identity_service):
    earlier = datetime.now(timezone.utc) - timedelta(days=60)
    now = datetime.now(timezone.utc)
    url = f"https://example.com/evolution-article-{int(now.timestamp())}"

    # 1. Document first seeded from historical archive
    archive_content = "Historical text version 1."
    arch_ids = identity_service.resolve_identities(url, archive_content)

    decision_arch, _ = identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=arch_ids["canonical_url"],
        doc_id=arch_ids["doc_id"],
        domain=arch_ids["domain"],
        title="Historical Article",
        snippet="Old text",
        content=archive_content,
        content_hash=arch_ids["content_hash"],
        source_type=SourceType.ARCHIVE_IMPORTER,
        source_captured_at=earlier,
    )
    assert decision_arch.action == "update_searchable"
    assert decision_arch.is_searchable is True

    # 2. Live crawl discovers fresh content today
    live_content = "Updated live version 2 from real web."
    live_ids = identity_service.resolve_identities(url, live_content)

    decision_live, _ = identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=live_ids["canonical_url"],
        doc_id=live_ids["doc_id"],
        domain=live_ids["domain"],
        title="Updated Live Article",
        snippet="New text",
        content=live_content,
        content_hash=live_ids["content_hash"],
        source_type=SourceType.LIVE_CRAWLER,
        live_fetched_at=now,
    )
    assert decision_live.action == "update_searchable"
    assert decision_live.is_searchable is True
    assert decision_live.version_seq == 2

    # Verify active source is now live_crawler
    db = get_db_manager().get_session()
    try:
        reg = db.query(DocumentRegistry).filter_by(doc_id=arch_ids["doc_id"]).first()
        assert reg.active_source_type == SourceType.LIVE_CRAWLER
        assert reg.version_sequence == 2
    finally:
        db.close()


def test_missing_timestamp_archive_does_not_overwrite_live(identity_service):
    now = datetime.now(timezone.utc)
    url = f"https://example.com/undated-page-{int(now.timestamp())}"

    # Seed live
    content_live = "Live content with known timestamp."
    ids_live = identity_service.resolve_identities(url, content_live)

    identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=ids_live["canonical_url"],
        doc_id=ids_live["doc_id"],
        domain=ids_live["domain"],
        title="Live Page",
        snippet="Snippet",
        content=content_live,
        content_hash=ids_live["content_hash"],
        source_type=SourceType.LIVE_CRAWLER,
        live_fetched_at=now,
    )

    # Ingest archive record with NO timestamp
    content_arch = "Archive record with missing timestamp."
    ids_arch = identity_service.resolve_identities(url, content_arch)

    decision_arch, _ = identity_service.record_capture_and_registry(
        raw_url=url,
        canonical_url=ids_arch["canonical_url"],
        doc_id=ids_arch["doc_id"],
        domain=ids_arch["domain"],
        title="Unknown Timestamp Page",
        snippet="Snippet",
        content=content_arch,
        content_hash=ids_arch["content_hash"],
        source_type=SourceType.ARCHIVE_IMPORTER,
        source_captured_at=None,
    )

    assert decision_arch.action == "archive_capture_only"
    assert decision_arch.is_searchable is False


def test_alias_management_preserves_alternate_url(identity_service):
    canonical_url = "https://example.com/article"
    alternate_url = "https://example.com/article?redirect=true"
    content = "Article text about algorithms."
    ids = identity_service.resolve_identities(alternate_url, content, canonical_hint=canonical_url)

    decision, _ = identity_service.record_capture_and_registry(
        raw_url=alternate_url,
        canonical_url=canonical_url,
        doc_id=ids["doc_id"],
        domain="example.com",
        title="Article",
        snippet="Snippet",
        content=content,
        content_hash=ids["content_hash"],
        source_type=SourceType.LIVE_CRAWLER,
        http_status=301,
    )

    db = get_db_manager().get_session()
    try:
        alias = db.query(DocumentAlias).filter_by(alternate_url=alternate_url).first()
        assert alias is not None
        assert alias.doc_id == ids["doc_id"]
        assert alias.alias_type == "canonical_redirect"
    finally:
        db.close()
