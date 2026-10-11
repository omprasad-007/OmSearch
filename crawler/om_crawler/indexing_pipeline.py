import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.schemas.document import DocumentModel
from app.repositories.opensearch_repo import OpenSearchRepository, get_opensearch_repo
from app.repositories.database import get_db_manager, URLRecord, DocumentLifecycle
from app.ingestion.normalizer import compute_url_id, generate_snippet
from crawler.om_crawler.extractor import ExtractedDocument

logger = logging.getLogger(__name__)


class CrawlerIndexingService:
    """
    Integrates crawler output with OpenSearch and PostgreSQL lifecycle records.
    Implements multi-level deduplication and incremental indexing:
    - Skips redundant OpenSearch writes if content hash is unchanged.
    - Updates existing documents idempotently when content changes.
    - Records lifecycle trace.
    """

    def __init__(self, os_repo: Optional[OpenSearchRepository] = None):
        self.os_repo = os_repo or get_opensearch_repo()
        self.db_mgr = get_db_manager()

    def process_and_index(self, doc: ExtractedDocument, url_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Takes an extracted document, checks for existing content hash,
        and performs incremental indexing.
        """
        db = self.db_mgr.get_session()
        target_canonical = doc.canonical_url or doc.final_url
        doc_id = compute_url_id(target_canonical)

        try:
            # Check existing URL record and content hash in DB
            existing_url = (
                db.query(URLRecord).filter(URLRecord.id == url_id).first()
                if url_id
                else db.query(URLRecord).filter(URLRecord.url == doc.url).first()
            )

            # Check if identical content exists elsewhere
            duplicate_content_url = (
                db.query(URLRecord)
                .filter(
                    URLRecord.content_hash == doc.content_hash,
                    URLRecord.id != (existing_url.id if existing_url else None),
                )
                .first()
                if doc.content_hash
                else None
            )

            now = datetime.now(timezone.utc)

            # Case 1: Identical content exists under another URL
            if duplicate_content_url:
                logger.info(
                    "Content deduplication: URL %s duplicates %s (hash %s)",
                    doc.url, duplicate_content_url.url, doc.content_hash[:8]
                )
                if existing_url:
                    existing_url.content_hash = doc.content_hash
                    existing_url.canonical_url = duplicate_content_url.canonical_url or duplicate_content_url.url
                    existing_url.last_fetched_at = now
                    existing_url.updated_at = now

                db.add(
                    DocumentLifecycle(
                        url_id=existing_url.id if existing_url else None,
                        canonical_url=target_canonical,
                        action="deduplicated",
                        status="warning",
                        details=json.dumps({"matched_url": duplicate_content_url.url, "hash": doc.content_hash}),
                    )
                )
                db.commit()
                return {
                    "status": "duplicate",
                    "doc_id": doc_id,
                    "matched_url": duplicate_content_url.url,
                    "indexed": False,
                }

            # Case 2: Content has not changed since last crawl of this exact URL
            if existing_url and existing_url.content_hash == doc.content_hash and existing_url.indexed_at:
                logger.info("Content unchanged for %s. Skipping redundant OpenSearch write.", doc.url)
                existing_url.last_fetched_at = now
                existing_url.updated_at = now
                db.add(
                    DocumentLifecycle(
                        url_id=existing_url.id,
                        canonical_url=target_canonical,
                        action="fetched_unchanged",
                        status="success",
                        details=json.dumps({"hash": doc.content_hash}),
                    )
                )
                db.commit()
                return {
                    "status": "unchanged",
                    "doc_id": doc_id,
                    "indexed": False,
                }

            # Case 3: New or updated content -> Index to OpenSearch
            snippet = doc.meta_description or generate_snippet(doc.main_text)

            doc_model = DocumentModel(
                id=doc_id,
                url=doc.url,
                canonical_url=target_canonical,
                domain=doc.domain,
                title=doc.title,
                content=doc.main_text,
                snippet=snippet,
                language=doc.language or "en",
                published_at=doc.published_at,
                fetched_at=doc.fetched_at,
                indexed_at=now,
                content_hash=doc.content_hash,
                http_status=doc.http_status,
                document_type="webpage",
            )

            # Write to OpenSearch (or fallback repository cache)
            os_remote_success = self.os_repo.index_document(doc_model)
            index_success = os_remote_success or (doc_model.id in getattr(self.os_repo, "_fallback_store", {}))

            # Update database URL record
            if existing_url:
                existing_url.content_hash = doc.content_hash
                existing_url.canonical_url = target_canonical
                existing_url.last_fetched_at = now
                existing_url.indexed_at = now
                existing_url.updated_at = now

            db.add(
                DocumentLifecycle(
                    url_id=existing_url.id if existing_url else None,
                    canonical_url=target_canonical,
                    action="indexed" if index_success else "index_error",
                    status="success" if index_success else "failure",
                    details=json.dumps({"title": doc.title, "length": len(doc.main_text)}),
                )
            )
            db.commit()

            return {
                "status": "indexed" if index_success else "index_failed",
                "doc_id": doc_id,
                "title": doc.title,
                "indexed": index_success,
            }

        except Exception as e:
            db.rollback()
            logger.exception("Indexing pipeline error for %s: %s", doc.url, e)
            return {
                "status": "error",
                "doc_id": doc_id,
                "error": str(e),
                "indexed": False,
            }
        finally:
            db.close()
