import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from sqlalchemy import text, and_, or_, func
from sqlalchemy.orm import Session

from app.repositories.database import (
    get_db_manager,
    URLRecord,
    FrontierStatus,
    DocumentLifecycle,
)
from crawler.om_crawler.url_normalizer import URLNormalizer

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 90
MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 300.0


class FrontierManager:
    """
    Durable PostgreSQL and SQLite backed crawl frontier manager.
    Handles atomic worker leases, per-host politeness, exponential backoff,
    duplicate suppression, and crash recovery.
    """

    def __init__(self, normalizer: Optional[URLNormalizer] = None):
        self.db_mgr = get_db_manager()
        self.normalizer = normalizer or URLNormalizer()

    def enqueue_urls(
        self,
        urls: List[str],
        parent_url: Optional[str] = None,
        depth: int = 0,
        priority: int = 0,
    ) -> Dict[str, int]:
        """
        Normalize and insert new URLs into the frontier.
        Suppresses duplicate entries.
        """
        db = self.db_mgr.get_session()
        stats = {"discovered": 0, "duplicates": 0, "skipped": 0}
        seen_in_batch: set[str] = set()

        try:
            for raw_url in urls:
                norm_url = self.normalizer.normalize(raw_url, base_url=parent_url)
                if not norm_url:
                    stats["skipped"] += 1
                    continue

                # Check intra-batch duplicate
                if norm_url in seen_in_batch or raw_url in seen_in_batch:
                    stats["duplicates"] += 1
                    continue

                is_eligible, reason = self.normalizer.is_crawlable(norm_url, current_depth=depth)
                if not is_eligible:
                    stats["skipped"] += 1
                    continue

                parsed = urlparse(norm_url)
                domain = parsed.hostname or ""
                scheme = parsed.scheme or "https"

                # Check if URL or normalized URL already exists in database
                existing = (
                    db.query(URLRecord)
                    .filter(or_(URLRecord.url == raw_url, URLRecord.normalized_url == norm_url))
                    .first()
                )

                if existing:
                    stats["duplicates"] += 1
                    seen_in_batch.add(norm_url)
                    seen_in_batch.add(raw_url)
                    continue

                seen_in_batch.add(norm_url)
                seen_in_batch.add(raw_url)

                now = datetime.now(timezone.utc)
                record = URLRecord(
                    url=raw_url,
                    normalized_url=norm_url,
                    canonical_url=norm_url,
                    domain=domain,
                    scheme=scheme,
                    discovery_source=parent_url,
                    depth=depth,
                    status=FrontierStatus.QUEUED,
                    priority=priority,
                    attempt_count=0,
                    next_fetch_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(record)
                stats["discovered"] += 1

            db.commit()
            return stats
        except Exception as e:
            db.rollback()
            logger.exception("Frontier enqueue error: %s", e)
            raise
        finally:
            db.close()

    def reset_expired_leases(self) -> int:
        """
        Reclaim leases from dead workers or interrupted jobs.
        If a record is stuck in FETCHING with lease_expires_at < now(), revert to QUEUED.
        """
        db = self.db_mgr.get_session()
        try:
            now = datetime.now(timezone.utc)
            expired = (
                db.query(URLRecord)
                .filter(
                    URLRecord.status == FrontierStatus.FETCHING,
                    URLRecord.lease_expires_at < now,
                )
                .all()
            )
            count = len(expired)
            for rec in expired:
                rec.status = FrontierStatus.QUEUED
                rec.worker_id = None
                rec.lease_expires_at = None
                rec.updated_at = now
            db.commit()
            if count > 0:
                logger.info("Reclaimed %d expired worker leases in crawl frontier.", count)
            return count
        except Exception as e:
            db.rollback()
            logger.error("Failed to reset expired leases: %s", e)
            return 0
        finally:
            db.close()

    def claim_batch(
        self,
        worker_id: str,
        batch_size: int = 10,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_per_host: int = 1,
        allowed_domains: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Atomically claim next available URLs for processing by worker_id.
        Enforces per-host limit so only 1 URL per domain is active concurrently.
        """
        # First recover any orphaned expired leases
        self.reset_expired_leases()

        db = self.db_mgr.get_session()
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)

        claimed_records: List[Dict[str, Any]] = []

        try:
            # Check which domains are already currently being fetched
            active_domains = {
                row[0]
                for row in db.query(URLRecord.domain)
                .filter(URLRecord.status == FrontierStatus.FETCHING)
                .all()
            }

            # Query candidate URLs eligible for crawling
            query = (
                db.query(URLRecord)
                .filter(
                    or_(
                        URLRecord.status == FrontierStatus.QUEUED,
                        and_(
                            URLRecord.status == FrontierStatus.RETRY_WAIT,
                            URLRecord.next_fetch_at <= now,
                        ),
                    )
                )
            )

            if allowed_domains:
                clean_allowed = [d.split(":")[0].lower() for d in allowed_domains if d]
                query = query.filter(URLRecord.domain.in_(clean_allowed))

            query = query.order_by(URLRecord.priority.desc(), URLRecord.depth.asc(), URLRecord.id.asc())

            # PostgreSQL row-level lock support
            if not self.db_mgr.is_sqlite:
                query = query.with_for_update(skip_locked=True)

            candidates = query.limit(batch_size * 5).all()

            seen_batch_domains = set()
            for rec in candidates:
                if len(claimed_records) >= batch_size:
                    break

                # Enforce per-host politeness: skip if domain is currently being fetched
                if rec.domain in active_domains or rec.domain in seen_batch_domains:
                    continue

                # Claim the lease
                rec.status = FrontierStatus.FETCHING
                rec.worker_id = worker_id
                rec.lease_expires_at = lease_until
                rec.attempt_count = (rec.attempt_count or 0) + 1
                rec.updated_at = now

                seen_batch_domains.add(rec.domain)
                claimed_records.append({
                    "id": rec.id,
                    "url": rec.url,
                    "normalized_url": rec.normalized_url or rec.url,
                    "domain": rec.domain,
                    "depth": rec.depth or 0,
                    "attempt_count": rec.attempt_count,
                    "discovery_source": rec.discovery_source,
                })

            db.commit()
            return claimed_records
        except Exception as e:
            db.rollback()
            logger.exception("Failed to claim frontier batch for worker %s: %s", worker_id, e)
            return []
        finally:
            db.close()

    def mark_fetched(
        self,
        url_id: int,
        http_status: int,
        content_hash: str,
        canonical_url: Optional[str] = None,
    ) -> None:
        """Mark URL record as successfully fetched."""
        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.id == url_id).first()
            if rec:
                now = datetime.now(timezone.utc)
                rec.status = FrontierStatus.FETCHED
                rec.http_status = http_status
                rec.content_hash = content_hash
                if canonical_url:
                    rec.canonical_url = canonical_url
                rec.last_fetched_at = now
                rec.worker_id = None
                rec.lease_expires_at = None
                rec.updated_at = now
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to mark URL %d as fetched: %s", url_id, e)
        finally:
            db.close()

    def mark_failed(
        self,
        url_id: int,
        error_message: str,
        http_status: Optional[int] = None,
        is_transient: bool = True,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        """
        Record fetch failure with exponential backoff if transient,
        or mark FAILED if permanent or max attempts exceeded.
        """
        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.id == url_id).first()
            if not rec:
                return

            now = datetime.now(timezone.utc)
            rec.last_error = error_message
            rec.worker_id = None
            rec.lease_expires_at = None
            rec.updated_at = now
            if http_status:
                rec.http_status = http_status

            attempts = rec.attempt_count or 1

            if is_transient and attempts < MAX_ATTEMPTS:
                # Calculate backoff delay with jitter
                if retry_after_seconds:
                    delay = max(1.0, float(retry_after_seconds))
                else:
                    exp_delay = BASE_BACKOFF_SECONDS * (2 ** (attempts - 1))
                    jitter = random.uniform(0.5, 2.0)
                    delay = min(MAX_BACKOFF_SECONDS, exp_delay + jitter)

                rec.status = FrontierStatus.RETRY_WAIT
                rec.next_fetch_at = now + timedelta(seconds=delay)
                logger.warning(
                    "URL %s transient failure (attempt %d/%d). Scheduled retry in %.1fs: %s",
                    rec.url, attempts, MAX_ATTEMPTS, delay, error_message,
                )
            else:
                rec.status = FrontierStatus.FAILED
                logger.error("URL %s permanently failed: %s", rec.url, error_message)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to record failure for URL %d: %s", url_id, e)
        finally:
            db.close()

    def mark_skipped(self, url_id: int, reason: str, status: str = FrontierStatus.SKIPPED_POLICY) -> None:
        """Mark URL as skipped by policy, robots.txt, or duplicate."""
        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.id == url_id).first()
            if rec:
                now = datetime.now(timezone.utc)
                rec.status = status
                rec.last_error = reason
                rec.worker_id = None
                rec.lease_expires_at = None
                rec.updated_at = now
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to mark URL %d as skipped: %s", url_id, e)
        finally:
            db.close()

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate frontier counts by status."""
        db = self.db_mgr.get_session()
        try:
            rows = (
                db.query(URLRecord.status, func.count(URLRecord.id))
                .group_by(URLRecord.status)
                .all()
            )
            counts = {status: 0 for status in [
                FrontierStatus.DISCOVERED,
                FrontierStatus.QUEUED,
                FrontierStatus.FETCHING,
                FrontierStatus.FETCHED,
                FrontierStatus.SKIPPED_POLICY,
                FrontierStatus.RETRY_WAIT,
                FrontierStatus.FAILED,
                FrontierStatus.BLOCKED,
                FrontierStatus.DUPLICATE,
            ]}
            total = 0
            for st, cnt in rows:
                if st:
                    counts[st] = cnt
                    total += cnt

            total_domains = db.query(func.count(func.distinct(URLRecord.domain))).scalar() or 0

            return {
                "total_urls": total,
                "total_domains": total_domains,
                "by_status": counts,
            }
        finally:
            db.close()
