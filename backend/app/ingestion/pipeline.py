import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

from app.schemas.document import DocumentModel
from app.repositories.opensearch_repo import OpenSearchRepository, get_opensearch_repo
from app.repositories.database import (
    get_db_manager,
    URLRecord,
    DocumentLifecycle,
    CrawlJob,
)
from app.ingestion.normalizer import (
    normalize_url,
    extract_domain,
    compute_url_id,
    compute_content_hash,
    generate_snippet,
)

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        os_repo: Optional[OpenSearchRepository] = None,
    ):
        self.os_repo = os_repo or get_opensearch_repo()
        self.db_manager = get_db_manager()

    def process_raw_document(self, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process, normalize, deduplicate, record, and index a single document.
        Catches errors per document to ensure the batch never crashes.
        """
        raw_url = raw_item.get("url", "")
        if not raw_url:
            return {"status": "skipped", "reason": "Missing URL"}

        try:
            canonical_url = normalize_url(raw_url)
            domain = extract_domain(canonical_url)
            doc_id = compute_url_id(canonical_url)

            # Extract or clean content
            title = (raw_item.get("title") or "").strip()
            content = raw_item.get("content", "")
            raw_html = raw_item.get("raw_html")

            if raw_html and not content:
                soup = BeautifulSoup(raw_html, "html.parser")
                # Remove scripts and styles
                for tag in soup(["script", "style", "noscript", "svg"]):
                    tag.decompose()
                if not title and soup.title and soup.title.string:
                    title = soup.title.string.strip()
                content = soup.get_text(separator=" ", strip=True)

            content = content.strip()
            if not title:
                title = raw_item.get("title") or domain

            content_hash = compute_content_hash(content)
            snippet = raw_item.get("snippet") or generate_snippet(content)

            # Check database for deduplication and status tracking
            db = self.db_manager.get_session()
            try:
                existing_url = db.query(URLRecord).filter(URLRecord.canonical_url == canonical_url).first()
                duplicate_content = (
                    db.query(URLRecord).filter(URLRecord.content_hash == content_hash).first()
                    if content_hash
                    else None
                )

                if duplicate_content and (not existing_url or duplicate_content.id != existing_url.id):
                    # Duplicate content detected
                    logger.info("Duplicate content detected for '%s' (matches '%s')", canonical_url, duplicate_content.canonical_url)
                    db.add(
                        DocumentLifecycle(
                            url_id=existing_url.id if existing_url else None,
                            canonical_url=canonical_url,
                            action="deduplicated",
                            status="warning",
                            details=json.dumps({"matched_url": duplicate_content.canonical_url}),
                        )
                    )
                    db.commit()
                    return {
                        "status": "duplicate",
                        "url": canonical_url,
                        "matched_url": duplicate_content.canonical_url,
                    }

                # Create or update URL record
                now = datetime.now(timezone.utc)
                if not existing_url:
                    existing_url = URLRecord(
                        url=raw_url,
                        canonical_url=canonical_url,
                        domain=domain,
                        status="indexed",
                        http_status=raw_item.get("http_status", 200),
                        content_hash=content_hash,
                        last_fetched_at=now,
                        indexed_at=now,
                    )
                    db.add(existing_url)
                else:
                    existing_url.status = "indexed"
                    existing_url.content_hash = content_hash
                    existing_url.last_fetched_at = now
                    existing_url.indexed_at = now

                db.flush()

                # Parse publication date if present
                pub_date = None
                if raw_item.get("published_at"):
                    try:
                        pub_date = datetime.fromisoformat(raw_item["published_at"])
                    except Exception:
                        pass

                # Build DocumentModel
                doc = DocumentModel(
                    id=doc_id,
                    url=raw_url,
                    canonical_url=canonical_url,
                    domain=domain,
                    title=title,
                    content=content,
                    snippet=snippet,
                    language=raw_item.get("language", "en"),
                    published_at=pub_date,
                    fetched_at=now,
                    indexed_at=now,
                    content_hash=content_hash,
                    http_status=raw_item.get("http_status", 200),
                    document_type=raw_item.get("document_type", "webpage"),
                )

                # Index into OpenSearch (or fallback cache)
                self.os_repo.index_document(doc)

                # Record successful lifecycle
                db.add(
                    DocumentLifecycle(
                        url_id=existing_url.id,
                        canonical_url=canonical_url,
                        action="indexed",
                        status="success",
                        details=json.dumps({"title": title, "length": len(content)}),
                    )
                )
                db.commit()

                return {
                    "status": "indexed",
                    "id": doc_id,
                    "url": canonical_url,
                    "title": title,
                }
            except Exception as dbe:
                db.rollback()
                logger.error("DB error processing '%s': %s", canonical_url, dbe)
                raise
            finally:
                db.close()

        except Exception as e:
            logger.exception("Failed to ingest document '%s': %s", raw_url, e)
            return {
                "status": "failed",
                "url": raw_url,
                "error": str(e),
            }

    def ingest_corpus(self, documents: List[Dict[str, Any]], job_type: str = "sample_corpus") -> Dict[str, Any]:
        """Ingest a batch of documents, logging crawl job progress."""
        db = self.db_manager.get_session()
        job = CrawlJob(
            job_type=job_type,
            status="running",
            total_urls=len(documents),
            processed_urls=0,
            failed_urls=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        db.close()

        results = []
        indexed_count = 0
        duplicate_count = 0
        failed_count = 0

        for doc_item in documents:
            res = self.process_raw_document(doc_item)
            results.append(res)
            st = res.get("status")
            if st == "indexed":
                indexed_count += 1
            elif st == "duplicate":
                duplicate_count += 1
            else:
                failed_count += 1

        # Finalize job status
        db = self.db_manager.get_session()
        try:
            job_rec = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            if job_rec:
                job_rec.processed_urls = indexed_count + duplicate_count
                job_rec.failed_urls = failed_count
                job_rec.status = "completed" if failed_count == 0 else "completed_with_errors"
                job_rec.finished_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

        return {
            "job_id": job_id,
            "total": len(documents),
            "indexed": indexed_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "results": results,
        }
