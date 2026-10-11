"""
OM Search - Recrawl Policy & Freshness Manager
Computes dynamic recrawl schedules, handles HTTP 304 Not Modified validation,
and ensures recrawl failures do not erase valid indexed documents.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from app.repositories.database import get_db_manager, URLRecord, DocumentLifecycle
from app.ingestion.normalizer import normalize_url

logger = logging.getLogger("om_ingestion.recrawl")


class RecrawlPolicyManager:
    """
    Determines next fetch schedules for existing URLs without unnecessary re-fetching.
    """

    def __init__(self, db_manager=None):
        self.db_mgr = db_manager or get_db_manager()

    def compute_next_interval(
        self,
        domain: str,
        observed_change: bool = False,
        consecutive_unchanged: int = 0,
    ) -> timedelta:
        """
        Adaptive recrawl scheduling:
        - Recently changed content: recrawl sooner (e.g., 24-48 hours).
        - Stable encyclopedia / reference: step up interval (up to 14 days).
        """
        if observed_change:
            return timedelta(days=1)
        
        # Step up based on unchanged frequency
        days = min(14, 3 + (consecutive_unchanged * 2))
        return timedelta(days=days)

    def handle_not_modified(self, url: str) -> bool:
        """
        Handles HTTP 304 (Not Modified).
        Updates validation timestamp without replacing or erasing existing document text.
        """
        canon_url = normalize_url(url)
        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.canonical_url == canon_url).first()
            if rec:
                now = datetime.now(timezone.utc)
                rec.last_fetched_at = now
                rec.next_fetch_at = now + self.compute_next_interval(rec.domain, observed_change=False)
                rec.updated_at = now

                db.add(
                    DocumentLifecycle(
                        url_id=rec.id,
                        canonical_url=canon_url,
                        action="revalidated_304",
                        status="success",
                        details="Content confirmed unchanged via HTTP 304 Not Modified",
                    )
                )
                db.commit()
                logger.info("URL %s validated via HTTP 304 (content retained intact).", canon_url)
                return True
            return False
        finally:
            db.close()

    def handle_recrawl_failure(self, url: str, error: str) -> bool:
        """
        Handles transient or permanent recrawl failure.
        Preserves existing valid search document while recording error in frontier.
        """
        canon_url = normalize_url(url)
        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.canonical_url == canon_url).first()
            if rec:
                now = datetime.now(timezone.utc)
                rec.last_error = f"Recrawl failed: {error}"
                # Schedule retry later without marking previous content invalid
                rec.next_fetch_at = now + timedelta(hours=6)
                rec.updated_at = now

                db.add(
                    DocumentLifecycle(
                        url_id=rec.id,
                        canonical_url=canon_url,
                        action="recrawl_failure_preserved",
                        status="warning",
                        details=f"Recrawl error encountered; existing indexed version preserved: {error}",
                    )
                )
                db.commit()
                logger.warning("Recrawl failed for %s (%s). Existing index document preserved.", canon_url, error)
                return True
            return False
        finally:
            db.close()
