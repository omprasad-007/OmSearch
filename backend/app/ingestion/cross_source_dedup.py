"""
OM Search - Cross-Source Deduplication & Coordination Service
Coordinates between live crawler and archive importer to prevent redundant work,
preserve multi-source provenance, and maintain non-destructive recrawl schedules.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.repositories.database import (
    get_db_manager,
    URLRecord,
    DocumentRegistry,
    HistoricalCapture,
    DocumentAlias,
    FrontierStatus,
    SourceType,
)
from app.ingestion.normalizer import normalize_url, compute_url_id, compute_content_hash

logger = logging.getLogger("om_ingestion.cross_source")


class CrossSourceDeduplicationService:
    """
    Ensures safe cross-pollination between live and historical sources without redundancy.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self._external_session = db_session
        self.db_mgr = get_db_manager()

    def _get_session(self) -> Session:
        return self._external_session or self.db_mgr.get_session()

    def handle_archive_url_discovery(
        self,
        archive_url: str,
        source_captured_at: Optional[datetime],
        schedule_live_verification: bool = True,
    ) -> Dict[str, Any]:
        """
        Invoked when an archive record reveals a URL.
        Checks if already known to the live crawler frontier:
        - If live crawler already fetched it recently: does not clobber live schedule.
        - If unknown: enqueues into frontier with routine priority for live freshness.
        """
        canon_url = normalize_url(archive_url)
        doc_id = compute_url_id(canon_url)
        db = self._get_session()
        owns_session = self._external_session is None

        try:
            # Check existing live frontier record
            url_rec = db.query(URLRecord).filter(URLRecord.canonical_url == canon_url).first()

            if url_rec:
                # URL already known to live crawler
                live_fetched = url_rec.last_fetched_at
                is_newer_live = bool(live_fetched and source_captured_at and live_fetched >= source_captured_at)

                return {
                    "action": "preserve_live_schedule",
                    "url": canon_url,
                    "doc_id": doc_id,
                    "already_in_frontier": True,
                    "live_status": url_rec.status,
                    "live_is_newer": is_newer_live,
                }

            # URL is new to live crawler: schedule live discovery
            if schedule_live_verification:
                from urllib.parse import urlparse
                domain = urlparse(canon_url).hostname or ""
                now = datetime.now(timezone.utc)

                new_rec = URLRecord(
                    url=archive_url,
                    normalized_url=canon_url,
                    canonical_url=canon_url,
                    domain=domain,
                    scheme=urlparse(canon_url).scheme or "https",
                    discovery_source="archive_provenance",
                    depth=1,
                    status=FrontierStatus.QUEUED,
                    priority=0,
                    next_fetch_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_rec)
                if owns_session:
                    db.commit()

                return {
                    "action": "enqueued_for_live_verification",
                    "url": canon_url,
                    "doc_id": doc_id,
                    "already_in_frontier": False,
                }

            return {
                "action": "archive_only_recorded",
                "url": canon_url,
                "doc_id": doc_id,
                "already_in_frontier": False,
            }

        finally:
            if owns_session:
                db.close()

    def handle_live_url_discovery(
        self,
        live_url: str,
        content_hash: str,
    ) -> Dict[str, Any]:
        """
        Invoked when live crawler fetches a URL.
        Associates with existing historical captures and updates searchable registry.
        """
        canon_url = normalize_url(live_url)
        doc_id = compute_url_id(canon_url)
        db = self._get_session()
        owns_session = self._external_session is None

        try:
            # Check for existing captures
            historical_count = db.query(HistoricalCapture).filter(HistoricalCapture.canonical_url == canon_url).count()
            registry = db.query(DocumentRegistry).filter(DocumentRegistry.doc_id == doc_id).first()

            return {
                "doc_id": doc_id,
                "canonical_url": canon_url,
                "has_historical_captures": historical_count > 0,
                "historical_capture_count": historical_count,
                "registered": registry is not None,
                "active_source": registry.active_source_type if registry else None,
            }
        finally:
            if owns_session:
                db.close()
