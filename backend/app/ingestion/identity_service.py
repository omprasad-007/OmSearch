"""
OM Search - Shared Document Identity & Version Conflict Service
Implements canonical document identity strategy, source provenance tracking,
and source-aware version reconciliation rules between live and archive sources.
"""
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, NamedTuple
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from app.repositories.database import (
    URLRecord,
    DocumentRegistry,
    DocumentAlias,
    HistoricalCapture,
    SourceType,
    get_db_manager,
)
from app.ingestion.normalizer import (
    normalize_url,
    extract_domain,
    compute_url_id,
    compute_content_hash,
)

logger = logging.getLogger("om_ingestion.identity")


class VersionDecision(NamedTuple):
    action: str  # "update_searchable", "archive_capture_only", "skip_identical", "conflict_logged"
    reason: str
    is_searchable: bool
    version_seq: int
    capture_id: str


class DocumentIdentityService:
    """
    Manages URL identity, canonical identity, historical captures,
    and deterministic source-aware version reconciliation.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self._external_session = db_session
        self.db_mgr = get_db_manager()

    def _get_session(self) -> Session:
        if self._external_session is not None:
            return self._external_session
        return self.db_mgr.get_session()

    def resolve_identities(
        self,
        raw_url: str,
        content: str,
        canonical_hint: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Derives canonical URL, document ID, domain, and content fingerprint.
        """
        canonical_target = canonical_hint or raw_url
        canonical_url = normalize_url(canonical_target)
        doc_id = compute_url_id(canonical_url)
        content_hash = compute_content_hash(content)
        domain = extract_domain(canonical_url)

        return {
            "raw_url": raw_url,
            "canonical_url": canonical_url,
            "doc_id": doc_id,
            "domain": domain,
            "content_hash": content_hash,
        }

    def evaluate_version_conflict(
        self,
        doc_id: str,
        incoming_source_type: str,
        incoming_content_hash: str,
        incoming_captured_at: Optional[datetime],
        incoming_fetched_at: Optional[datetime],
        existing_registry: Optional[DocumentRegistry],
    ) -> VersionDecision:
        """
        Deterministic reconciliation deciding whether an incoming record may update
        the active searchable index or should be stored as historical capture only.
        """
        capture_id = f"cap_{uuid.uuid4().hex[:16]}"

        if not existing_registry:
            # Case 1: Fresh document - first time seen
            return VersionDecision(
                action="update_searchable",
                reason="Initial document ingestion",
                is_searchable=True,
                version_seq=1,
                capture_id=capture_id,
            )

        # Case 2: Identical content hash
        if existing_registry.current_content_hash == incoming_content_hash:
            return VersionDecision(
                action="skip_identical",
                reason="Content fingerprint identical to current active representation",
                is_searchable=False,
                version_seq=existing_registry.version_sequence,
                capture_id=capture_id,
            )

        def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        # Timestamps for comparison
        existing_live_time = _to_utc(existing_registry.live_fetched_at)
        existing_cap_time = _to_utc(existing_registry.source_captured_at)
        incoming_time = _to_utc(incoming_captured_at or incoming_fetched_at)

        # Case 3: Archive record attempting to overwrite newer Live Crawler content
        if (
            incoming_source_type == SourceType.ARCHIVE_IMPORTER
            and existing_registry.active_source_type == SourceType.LIVE_CRAWLER
        ):
            if existing_live_time and incoming_time and incoming_time < existing_live_time:
                logger.info(
                    "Version conflict policy: Older archive record (%s) denied overwriting newer live content (%s) for doc %s",
                    incoming_time.isoformat(),
                    existing_live_time.isoformat(),
                    doc_id,
                )
                return VersionDecision(
                    action="archive_capture_only",
                    reason="Historical archive capture is older than active live content; preserved in capture history",
                    is_searchable=False,
                    version_seq=existing_registry.version_sequence,
                    capture_id=capture_id,
                )
            elif not incoming_time:
                # Ambiguous archive timestamp
                logger.warning("Archive record has missing timestamp for doc %s; preserving existing live representation", doc_id)
                return VersionDecision(
                    action="archive_capture_only",
                    reason="Historical archive missing capture timestamp; preserved as historical capture without displacing live document",
                    is_searchable=False,
                    version_seq=existing_registry.version_sequence,
                    capture_id=capture_id,
                )

        # Case 4: Live Crawler content superseding Archive Importer
        if (
            incoming_source_type == SourceType.LIVE_CRAWLER
            and existing_registry.active_source_type == SourceType.ARCHIVE_IMPORTER
        ):
            logger.info("Live crawl updated historical archive document %s with fresh live content", doc_id)
            return VersionDecision(
                action="update_searchable",
                reason="Live crawl supersedes historical archive representation",
                is_searchable=True,
                version_seq=existing_registry.version_sequence + 1,
                capture_id=capture_id,
            )

        # Case 5: Archive-to-Archive comparison
        if (
            incoming_source_type == SourceType.ARCHIVE_IMPORTER
            and existing_registry.active_source_type == SourceType.ARCHIVE_IMPORTER
        ):
            if incoming_time and existing_cap_time and incoming_time <= existing_cap_time:
                return VersionDecision(
                    action="archive_capture_only",
                    reason="Incoming archive capture is older than existing active archive capture",
                    is_searchable=False,
                    version_seq=existing_registry.version_sequence,
                    capture_id=capture_id,
                )

        # Default progression: update searchable document
        return VersionDecision(
            action="update_searchable",
            reason=f"Valid version progression from {incoming_source_type}",
            is_searchable=True,
            version_seq=existing_registry.version_sequence + 1,
            capture_id=capture_id,
        )

    def record_capture_and_registry(
        self,
        raw_url: str,
        canonical_url: str,
        doc_id: str,
        domain: str,
        title: str,
        snippet: str,
        content: str,
        content_hash: str,
        source_type: str,
        source_archive_id: Optional[str] = None,
        source_captured_at: Optional[datetime] = None,
        live_fetched_at: Optional[datetime] = None,
        http_status: int = 200,
        headers_json: Optional[str] = None,
    ) -> Tuple[VersionDecision, HistoricalCapture]:
        """
        Executes atomic registration, creates historical capture record,
        and applies version conflict policy.
        """
        db = self._get_session()
        owns_session = self._external_session is None

        try:
            # Query existing registry
            registry = db.query(DocumentRegistry).filter(DocumentRegistry.doc_id == doc_id).first()

            # Evaluate reconciliation policy
            decision = self.evaluate_version_conflict(
                doc_id=doc_id,
                incoming_source_type=source_type,
                incoming_content_hash=content_hash,
                incoming_captured_at=source_captured_at,
                incoming_fetched_at=live_fetched_at,
                existing_registry=registry,
            )

            now = datetime.now(timezone.utc)

            # 1. Create immutable historical capture
            capture = HistoricalCapture(
                capture_id=decision.capture_id,
                url=raw_url,
                canonical_url=canonical_url,
                source_type=source_type,
                source_archive_id=source_archive_id,
                source_captured_at=source_captured_at or live_fetched_at,
                content_hash=content_hash,
                title=title,
                snippet=snippet,
                content=content,
                http_status=http_status,
                headers_json=headers_json,
                is_searchable_current=1 if decision.is_searchable else 0,
                created_at=now,
            )
            db.add(capture)

            # 2. Record alternate URL alias if raw_url differs from canonical_url
            if raw_url != canonical_url:
                alias = db.query(DocumentAlias).filter(DocumentAlias.alternate_url == raw_url).first()
                if not alias:
                    db.add(
                        DocumentAlias(
                            doc_id=doc_id,
                            alternate_url=raw_url,
                            alias_type="canonical_redirect" if http_status in (301, 302, 307, 308) else "canonical_link",
                        )
                    )

            # 3. Update or create DocumentRegistry if searchable
            if decision.is_searchable:
                if not registry:
                    registry = DocumentRegistry(
                        doc_id=doc_id,
                        canonical_url=canonical_url,
                        primary_url=raw_url,
                        domain=domain,
                        current_content_hash=content_hash,
                        active_source_type=source_type,
                        active_capture_id=decision.capture_id,
                        source_captured_at=source_captured_at,
                        live_fetched_at=live_fetched_at,
                        indexed_at=now,
                        version_sequence=decision.version_seq,
                        reconciliation_status="pending_index",
                    )
                    db.add(registry)
                else:
                    registry.primary_url = raw_url
                    registry.current_content_hash = content_hash
                    registry.active_source_type = source_type
                    registry.active_capture_id = decision.capture_id
                    registry.source_captured_at = source_captured_at or registry.source_captured_at
                    if live_fetched_at:
                        registry.live_fetched_at = live_fetched_at
                    registry.version_sequence = decision.version_seq
                    registry.reconciliation_status = "pending_index"
                    registry.updated_at = now

            if owns_session:
                db.commit()

            return decision, capture

        except Exception as e:
            if owns_session:
                db.rollback()
            logger.exception("Error recording document identity for %s: %s", raw_url, e)
            raise
        finally:
            if owns_session:
                db.close()
