"""
OM Search - Live Crawler Source Adapter
Integrates Phase 2 live crawler, URL frontier, robots policy, and HTML extractor
into the unified ingestion platform contract.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import httpx

from app.repositories.database import (
    get_db_manager,
    URLRecord,
    FrontierStatus,
    SourceType,
)
from crawler.om_crawler.network_safety import (
    validate_url_security,
    is_allowed_content_type,
    MAX_RESPONSE_BYTES,
)
from crawler.om_crawler.url_normalizer import URLNormalizer
from crawler.om_crawler.robots_policy import RobotsPolicyManager, DEFAULT_USER_AGENT
from crawler.om_crawler.frontier import FrontierManager
from crawler.om_crawler.extractor import HTMLExtractor
from app.ingestion.adapters.base import BaseSourceAdapter, WorkUnit, ExtractedRecord

logger = logging.getLogger("om_ingestion.adapters.crawler")


class LiveCrawlerAdapter(BaseSourceAdapter):
    """
    Adapter wrapping the Phase 2 live crawl subsystem.
    """

    def __init__(
        self,
        rate_limit_delay: float = 1.0,
        concurrency_limit: int = 4,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._rate_limit_delay = rate_limit_delay
        self._concurrency_limit = concurrency_limit
        self.user_agent = user_agent
        self.normalizer = URLNormalizer()
        self.robots_mgr = RobotsPolicyManager(user_agent=user_agent, default_delay=rate_limit_delay)
        self.frontier = FrontierManager(normalizer=self.normalizer)
        self.extractor = HTMLExtractor(normalizer=self.normalizer)
        self.db_mgr = get_db_manager()

    @property
    def source_type(self) -> str:
        return SourceType.LIVE_CRAWLER

    @property
    def default_concurrency_limit(self) -> int:
        return self._concurrency_limit

    @property
    def rate_limit_delay(self) -> float:
        return self._rate_limit_delay

    def discover_work_units(self, batch_size: int = 50) -> List[WorkUnit]:
        """
        Discovers claimable URLs from the frontier database table.
        """
        db = self.db_mgr.get_session()
        try:
            now = datetime.now(timezone.utc)
            # Reclaim expired leases first
            self.frontier.reset_expired_leases()

            records = (
                db.query(URLRecord)
                .filter(
                    URLRecord.status.in_([FrontierStatus.QUEUED, FrontierStatus.RETRY_WAIT]),
                    URLRecord.next_fetch_at <= now,
                )
                .order_by(URLRecord.priority.desc(), URLRecord.next_fetch_at.asc())
                .limit(batch_size)
                .all()
            )

            units = []
            for r in records:
                units.append(
                    WorkUnit(
                        unit_id=str(r.id),
                        source_type=self.source_type,
                        work_type="url_fetch",
                        payload={"url": r.url, "depth": r.depth, "parent_url": r.discovery_source},
                        priority=r.priority,
                        created_at=r.created_at,
                    )
                )
            return units
        finally:
            db.close()

    def execute_work_unit(self, unit: WorkUnit) -> List[ExtractedRecord]:
        """
        Fetches the URL, validates safety and robots, extracts content,
        and returns ExtractedRecord with live fetch timestamp.
        """
        url = unit.payload.get("url")
        if not url:
            return []

        # 1. Network safety
        safe, reason = validate_url_security(url, check_dns=True)
        if not safe:
            raise PermissionError(f"Network safety rejection: {reason}")

        # 2. Robots check
        allowed, robot_reason = self.robots_mgr.is_allowed(url)
        if not allowed:
            raise PermissionError(f"Robots disallowed: {robot_reason}")

        domain = urlparse(url).hostname or ""
        self.robots_mgr.record_host_access(domain)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }

        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            final_url = str(resp.url)
            fetch_time = datetime.now(timezone.utc)

            if resp.status_code != 200:
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if not is_allowed_content_type(content_type):
                raise ValueError(f"Disallowed content type: {content_type}")

            if len(resp.content) > MAX_RESPONSE_BYTES:
                raise ValueError(f"Response size exceeded limit: {len(resp.content)} bytes")

            extracted = self.extractor.extract(
                html_content=resp.text,
                url=url,
                final_url=final_url,
                http_status=resp.status_code,
                content_type=content_type,
                fetched_at=fetch_time,
            )

            # Discover and queue outgoing links in frontier
            if extracted.outgoing_links:
                depth = unit.payload.get("depth", 0) + 1
                self.frontier.enqueue_urls(
                    urls=extracted.outgoing_links[:50],
                    parent_url=final_url,
                    depth=depth,
                    priority=max(0, unit.priority - 1),
                )

            return [
                ExtractedRecord(
                    url=final_url,
                    title=extracted.title or domain,
                    content=extracted.main_text or "",
                    snippet=extracted.meta_description or (extracted.main_text[:200] + "..."),
                    canonical_url=extracted.canonical_url or final_url,
                    live_fetched_at=fetch_time,
                    source_captured_at=fetch_time,
                    language=extracted.language or "en",
                    http_status=resp.status_code,
                    outgoing_links=extracted.outgoing_links or [],
                )
            ]

    def complete_work_unit(self, unit: WorkUnit, status: str, error: Optional[str] = None) -> None:
        """
        Updates the URLRecord in frontier database.
        """
        try:
            url_id = int(unit.unit_id)
        except ValueError:
            return

        db = self.db_mgr.get_session()
        try:
            rec = db.query(URLRecord).filter(URLRecord.id == url_id).first()
            if rec:
                now = datetime.now(timezone.utc)
                if status == "COMPLETED":
                    rec.status = FrontierStatus.FETCHED
                    rec.last_fetched_at = now
                    rec.last_error = None
                else:
                    rec.status = FrontierStatus.FAILED
                    rec.last_error = error
                rec.lease_owner = None
                rec.lease_expires_at = None
                rec.updated_at = now
                db.commit()
        finally:
            db.close()

    def classify_error(self, exception: Exception) -> str:
        """
        Classifies error into TRANSIENT (retryable) or PERMANENT.
        """
        if isinstance(exception, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)):
            return "TRANSIENT"
        if isinstance(exception, httpx.HTTPStatusError):
            code = exception.response.status_code
            if code in (429, 500, 502, 503, 504):
                return "TRANSIENT"
            return "PERMANENT"
        if isinstance(exception, PermissionError):  # Robots / SSRF
            return "PERMANENT"
        if isinstance(exception, ValueError):  # Content-type / size
            return "PERMANENT"
        return "TRANSIENT"

    def get_checkpoint(self) -> Dict[str, Any]:
        """
        Returns frontier progress counters.
        """
        db = self.db_mgr.get_session()
        try:
            total = db.query(URLRecord).count()
            fetched = db.query(URLRecord).filter(URLRecord.status == FrontierStatus.FETCHED).count()
            queued = db.query(URLRecord).filter(URLRecord.status.in_([FrontierStatus.QUEUED, FrontierStatus.RETRY_WAIT])).count()
            failed = db.query(URLRecord).filter(URLRecord.status == FrontierStatus.FAILED).count()
            return {
                "total_urls": total,
                "fetched_urls": fetched,
                "queued_urls": queued,
                "failed_urls": failed,
            }
        finally:
            db.close()
