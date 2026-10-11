import pytest
from datetime import datetime, timezone, timedelta
from app.repositories.database import get_db_manager, DocumentRegistry, HistoricalCapture, SourceType
from app.repositories.opensearch_repo import get_opensearch_repo
from app.ingestion.indexing_gateway import SharedIndexingGateway


@pytest.fixture
def gateway():
    return SharedIndexingGateway()


def test_single_document_indexing(gateway):
    url = f"https://example.com/gateway-test-{int(datetime.now().timestamp())}"
    title = "Quantum Computing Architecture Overview"
    content = "Quantum computing harnesses superposition and entanglement to solve discrete optimization."

    result = gateway.submit_document(
        raw_url=url,
        title=title,
        content=content,
        source_type=SourceType.LIVE_CRAWLER,
    )

    assert result["indexed"] is True
    assert result["doc_id"] is not None

    # Verify OpenSearch search
    os_repo = get_opensearch_repo()
    doc = os_repo.get_document(result["doc_id"])
    assert doc is not None
    assert doc.get("title") == title

    # Verify DocumentRegistry status
    db = get_db_manager().get_session()
    try:
        reg = db.query(DocumentRegistry).filter_by(doc_id=result["doc_id"]).first()
        assert reg is not None
        assert reg.reconciliation_status == "synced"
    finally:
        db.close()


def test_bulk_document_indexing(gateway):
    ts = int(datetime.now().timestamp())
    docs = [
        {
            "url": f"https://example.com/bulk-test-1-{ts}",
            "title": "Batch Document Alpha",
            "content": "Alpha content describing machine learning principles.",
            "source_type": SourceType.LIVE_CRAWLER,
        },
        {
            "url": f"https://example.com/bulk-test-2-{ts}",
            "title": "Batch Document Beta",
            "content": "Beta content detailing distributed indexing algorithms.",
            "source_type": SourceType.ARCHIVE_IMPORTER,
            "source_captured_at": datetime.now(timezone.utc) - timedelta(days=5),
        },
    ]

    summary = gateway.submit_batch(docs)
    assert summary["total"] == 2
    assert summary["indexed"] == 2
    assert summary["failed"] == 0


def test_reconciliation_of_unindexed_documents(gateway):
    # Simulate a document registered in PostgreSQL/SQLite where OpenSearch write didn't complete
    ts = int(datetime.now().timestamp())
    url = f"https://example.com/reconcile-test-{ts}"
    doc_id = f"reconcile_doc_{ts}"
    capture_id = f"cap_reconcile_{ts}"
    now = datetime.now(timezone.utc)

    db = get_db_manager().get_session()
    try:
        # Create HistoricalCapture
        cap = HistoricalCapture(
            capture_id=capture_id,
            url=url,
            canonical_url=url,
            source_type=SourceType.LIVE_CRAWLER,
            source_captured_at=now,
            content_hash="mock_hash_for_reconciliation_test",
            title="Reconciliation Recovery Page",
            snippet="Snippet for reconciliation test",
            content="Full body text of page that failed during initial index write.",
            http_status=200,
            is_searchable_current=1,
            created_at=now,
        )
        db.add(cap)

        # Create DocumentRegistry in pending_index state
        reg = DocumentRegistry(
            doc_id=doc_id,
            canonical_url=url,
            primary_url=url,
            domain="example.com",
            current_content_hash="mock_hash_for_reconciliation_test",
            active_source_type=SourceType.LIVE_CRAWLER,
            active_capture_id=capture_id,
            source_captured_at=now,
            live_fetched_at=now,
            version_sequence=1,
            reconciliation_status="pending_index",
            created_at=now,
        )
        db.add(reg)
        db.commit()
    finally:
        db.close()

    # Trigger reconciliation
    rec_result = gateway.reconcile_unindexed_documents(limit=50)
    assert rec_result["reconciled"] >= 1

    # Verify status transitioned to 'synced'
    db = get_db_manager().get_session()
    try:
        updated_reg = db.query(DocumentRegistry).filter_by(doc_id=doc_id).first()
        assert updated_reg.reconciliation_status == "synced"
    finally:
        db.close()

    # Verify document is now present in OpenSearch
    os_repo = get_opensearch_repo()
    indexed_doc = os_repo.get_document(doc_id)
    assert indexed_doc is not None
    assert indexed_doc.get("title") == "Reconciliation Recovery Page"
