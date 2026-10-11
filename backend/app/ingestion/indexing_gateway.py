"""
OM Search - Shared Indexing Gateway & Reconciliation Service
Provides schema validation, version-aware atomic indexing, partial failure recovery,
and bidirectional reconciliation between PostgreSQL/SQLite and OpenSearch.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from app.schemas.document import DocumentModel
from app.repositories.opensearch_repo import OpenSearchRepository, get_opensearch_repo
from app.repositories.database import (
    get_db_manager,
    DocumentRegistry,
    DocumentLifecycle,
    HistoricalCapture,
    SourceType,
)
from app.ingestion.normalizer import generate_snippet
from app.ingestion.identity_service import DocumentIdentityService, VersionDecision

logger = logging.getLogger("om_ingestion.gateway")


class SharedIndexingGateway:
    """
    Unified indexing gateway for both live crawler and bulk archive importer.
    Guarantees deterministic document IDs, source-aware versioning, batching,
    and partial-failure reconciliation.
    """

    def __init__(
        self,
        os_repo: Optional[OpenSearchRepository] = None,
        identity_service: Optional[DocumentIdentityService] = None,
    ):
        self.os_repo = os_repo or get_opensearch_repo()
        self.identity_service = identity_service or DocumentIdentityService()
        self.db_mgr = get_db_manager()

    def submit_document(
        self,
        raw_url: str,
        title: str,
        content: str,
        snippet: Optional[str] = None,
        canonical_hint: Optional[str] = None,
        source_type: str = SourceType.LIVE_CRAWLER,
        source_archive_id: Optional[str] = None,
        source_captured_at: Optional[datetime] = None,
        live_fetched_at: Optional[datetime] = None,
        language: str = "en",
        http_status: int = 200,
        published_at: Optional[datetime] = None,
        headers_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes a single document through normalization, identity resolution,
        historical capture persistence, version conflict check, and OpenSearch indexing.
        """
        # 1. Resolve canonical identity and fingerprint
        ids = self.identity_service.resolve_identities(
            raw_url=raw_url,
            content=content,
            canonical_hint=canonical_hint,
        )

        clean_snippet = snippet or generate_snippet(content)
        clean_title = title.strip() if title else ids["domain"]

        # 2. Record historical capture and evaluate version conflict
        decision, capture = self.identity_service.record_capture_and_registry(
            raw_url=ids["raw_url"],
            canonical_url=ids["canonical_url"],
            doc_id=ids["doc_id"],
            domain=ids["domain"],
            title=clean_title,
            snippet=clean_snippet,
            content=content,
            content_hash=ids["content_hash"],
            source_type=source_type,
            source_archive_id=source_archive_id,
            source_captured_at=source_captured_at,
            live_fetched_at=live_fetched_at,
            http_status=http_status,
            headers_json=headers_json,
        )

        db = self.db_mgr.get_session()
        try:
            # 3. If version conflict policy decided NOT to update searchable document
            if not decision.is_searchable:
                db.add(
                    DocumentLifecycle(
                        canonical_url=ids["canonical_url"],
                        action=f"capture_recorded_{decision.action}",
                        status="success",
                        details=json.dumps({"reason": decision.reason, "capture_id": decision.capture_id}),
                    )
                )
                db.commit()
                return {
                    "doc_id": ids["doc_id"],
                    "url": ids["canonical_url"],
                    "status": decision.action,
                    "indexed": False,
                    "reason": decision.reason,
                    "capture_id": decision.capture_id,
                }

            # 4. Construct validated DocumentModel
            now = datetime.now(timezone.utc)
            doc_model = DocumentModel(
                id=ids["doc_id"],
                url=ids["raw_url"],
                canonical_url=ids["canonical_url"],
                domain=ids["domain"],
                title=clean_title,
                content=content,
                snippet=clean_snippet,
                language=language or "en",
                published_at=published_at,
                fetched_at=live_fetched_at or now,
                indexed_at=now,
                content_hash=ids["content_hash"],
                http_status=http_status,
                document_type="archive_doc" if source_type == SourceType.ARCHIVE_IMPORTER else "webpage",
            )

            # 5. Index into OpenSearch / fallback store
            os_success = self.os_repo.index_document(doc_model)

            # 6. Update registry reconciliation status
            reg = db.query(DocumentRegistry).filter(DocumentRegistry.doc_id == ids["doc_id"]).first()
            if reg:
                reg.reconciliation_status = "synced"
                reg.indexed_at = now

            db.add(
                DocumentLifecycle(
                    canonical_url=ids["canonical_url"],
                    action="indexed",
                    status="success",
                    details=json.dumps({
                        "source": source_type,
                        "version": decision.version_seq,
                        "capture_id": decision.capture_id,
                    }),
                )
            )
            db.commit()

            return {
                "doc_id": ids["doc_id"],
                "url": ids["canonical_url"],
                "status": "indexed",
                "indexed": True,
                "version_seq": decision.version_seq,
                "capture_id": decision.capture_id,
            }

        except Exception as e:
            db.rollback()
            logger.error("Failed indexing document %s: %s", raw_url, e)
            return {
                "doc_id": ids["doc_id"],
                "url": ids["canonical_url"],
                "status": "index_failed",
                "indexed": False,
                "error": str(e),
            }
        finally:
            db.close()

    def submit_batch(
        self,
        documents: List[Dict[str, Any]],
        source_type: str = SourceType.ARCHIVE_IMPORTER,
        source_archive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        High-throughput batch submission for bulk archive partitions or crawler flushes.
        Handles partial failures gracefully without halting the batch.
        """
        indexed_count = 0
        skipped_count = 0
        failed_count = 0
        docs_to_index_models: List[DocumentModel] = []
        synced_doc_ids: List[str] = []

        now = datetime.now(timezone.utc)
        db = self.db_mgr.get_session()

        try:
            for item in documents:
                raw_url = item.get("url")
                if not raw_url:
                    skipped_count += 1
                    continue

                content = item.get("content", "")
                title = item.get("title", "")
                snippet = item.get("snippet") or generate_snippet(content)

                captured_at = None
                if item.get("source_captured_at"):
                    try:
                        captured_at = datetime.fromisoformat(item["source_captured_at"])
                    except Exception:
                        pass

                live_fetched_at = None
                if item.get("live_fetched_at"):
                    try:
                        live_fetched_at = datetime.fromisoformat(item["live_fetched_at"])
                    except Exception:
                        pass

                ids = self.identity_service.resolve_identities(
                    raw_url=raw_url,
                    content=content,
                    canonical_hint=item.get("canonical_url"),
                )

                decision, capture = self.identity_service.record_capture_and_registry(
                    raw_url=ids["raw_url"],
                    canonical_url=ids["canonical_url"],
                    doc_id=ids["doc_id"],
                    domain=ids["domain"],
                    title=title or ids["domain"],
                    snippet=snippet,
                    content=content,
                    content_hash=ids["content_hash"],
                    source_type=source_type,
                    source_archive_id=source_archive_id,
                    source_captured_at=captured_at,
                    live_fetched_at=live_fetched_at,
                    http_status=item.get("http_status", 200),
                )

                if decision.is_searchable:
                    model = DocumentModel(
                        id=ids["doc_id"],
                        url=ids["raw_url"],
                        canonical_url=ids["canonical_url"],
                        domain=ids["domain"],
                        title=title or ids["domain"],
                        content=content,
                        snippet=snippet,
                        language=item.get("language", "en"),
                        published_at=None,
                        fetched_at=live_fetched_at or now,
                        indexed_at=now,
                        content_hash=ids["content_hash"],
                        http_status=item.get("http_status", 200),
                        document_type="archive_doc" if source_type == SourceType.ARCHIVE_IMPORTER else "webpage",
                    )
                    docs_to_index_models.append(model)
                    synced_doc_ids.append(ids["doc_id"])
                    indexed_count += 1
                else:
                    skipped_count += 1

            # Bulk write searchable documents to OpenSearch / fallback store
            if docs_to_index_models:
                self.os_repo.index_documents_bulk(docs_to_index_models)

                # Mark registry entries as synced
                db.query(DocumentRegistry).filter(
                    DocumentRegistry.doc_id.in_(synced_doc_ids)
                ).update({"reconciliation_status": "synced", "indexed_at": now}, synchronize_session=False)

            db.commit()

        except Exception as e:
            db.rollback()
            logger.exception("Batch indexing error: %s", e)
            failed_count = len(documents) - (indexed_count + skipped_count)
        finally:
            db.close()

        return {
            "total": len(documents),
            "indexed": indexed_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }

    def reconcile_unindexed_documents(self, limit: int = 200) -> Dict[str, int]:
        """
        Reconciles documents where DB record exists but OpenSearch write failed or is pending.
        Ensures strict eventual consistency.
        """
        db = self.db_mgr.get_session()
        reconciled = 0
        try:
            pending_records = (
                db.query(DocumentRegistry)
                .filter(DocumentRegistry.reconciliation_status.in_(["pending_index", "failed"]))
                .limit(limit)
                .all()
            )

            for rec in pending_records:
                # Fetch active capture content
                capture = db.query(HistoricalCapture).filter(HistoricalCapture.capture_id == rec.active_capture_id).first()
                if not capture:
                    continue

                model = DocumentModel(
                    id=rec.doc_id,
                    url=rec.primary_url,
                    canonical_url=rec.canonical_url,
                    domain=rec.domain,
                    title=capture.title or rec.domain,
                    content=capture.content or "",
                    snippet=capture.snippet or "",
                    language="en",
                    published_at=None,
                    fetched_at=rec.live_fetched_at or datetime.now(timezone.utc),
                    indexed_at=datetime.now(timezone.utc),
                    content_hash=rec.current_content_hash,
                    http_status=capture.http_status or 200,
                    document_type="archive_doc" if rec.active_source_type == SourceType.ARCHIVE_IMPORTER else "webpage",
                )
                self.os_repo.index_document(model)
                rec.reconciliation_status = "synced"
                reconciled += 1

            db.commit()
            return {"reconciled": reconciled, "remaining_pending": len(pending_records) - reconciled}
        except Exception as e:
            db.rollback()
            logger.error("Reconciliation error: %s", e)
            return {"reconciled": reconciled, "error": str(e)}
        finally:
            db.close()

    def archive_and_index_batch(
        self,
        documents: List[Dict[str, Any]],
        source_type: str = "unified_stream",
        source_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Durable cloud batch pipeline:
        Compresses and archives to Google Drive (if connected) and indexes into OpenSearch.
        """
        from app.ingestion.drive_batch_pipeline import get_drive_batch_pipeline
        pipeline = get_drive_batch_pipeline()
        return pipeline.process_and_archive_batch(
            records=documents,
            source_type=source_type,
            source_reference=source_reference,
        )


_indexing_gateway_singleton = None


def get_indexing_gateway() -> SharedIndexingGateway:
    global _indexing_gateway_singleton
    if _indexing_gateway_singleton is None:
        _indexing_gateway_singleton = SharedIndexingGateway()
    return _indexing_gateway_singleton

