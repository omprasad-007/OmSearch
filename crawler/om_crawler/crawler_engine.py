import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import httpx

from app.repositories.database import get_db_manager, CrawlJob, FrontierStatus
from crawler.om_crawler.network_safety import (
    validate_url_security,
    is_allowed_content_type,
    MAX_RESPONSE_BYTES,
)
from crawler.om_crawler.url_normalizer import URLNormalizer
from crawler.om_crawler.robots_policy import RobotsPolicyManager, DEFAULT_USER_AGENT
from crawler.om_crawler.frontier import FrontierManager
from crawler.om_crawler.extractor import HTMLExtractor
from crawler.om_crawler.indexing_pipeline import CrawlerIndexingService

logger = logging.getLogger(__name__)


class CrawlerEngine:
    def __init__(
        self,
        job_id: int,
        seed_urls: List[str],
        max_pages: int = 50,
        max_depth: int = 3,
        allowed_domains: Optional[List[str]] = None,
        rate_limit_delay: float = 1.5,
        user_agent: str = DEFAULT_USER_AGENT,
        worker_id: Optional[str] = None,
    ):
        self.job_id = job_id
        self.seed_urls = seed_urls
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.allowed_domains = allowed_domains or [
            urlparse(s).hostname.lower() for s in seed_urls if urlparse(s).hostname
        ]
        self.rate_limit_delay = rate_limit_delay
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

        self.normalizer = URLNormalizer(
            allowed_domains=self.allowed_domains,
            max_depth=self.max_depth,
        )
        self.robots_mgr = RobotsPolicyManager(
            user_agent=user_agent,
            default_delay=rate_limit_delay,
        )
        self.frontier = FrontierManager(normalizer=self.normalizer)
        self.extractor = HTMLExtractor(normalizer=self.normalizer)
        self.indexer = CrawlerIndexingService()
        self.db_mgr = get_db_manager()

        self._stop_requested = False

    def check_job_status(self) -> str:
        """Read current status from DB to honor pause or cancel commands."""
        db = self.db_mgr.get_session()
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == self.job_id).first()
            if job:
                return job.status
            return "cancelled"
        finally:
            db.close()

    def update_job_progress(
        self,
        processed_inc: int = 0,
        indexed_inc: int = 0,
        failed_inc: int = 0,
        total_override: Optional[int] = None,
        final_status: Optional[str] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        db = self.db_mgr.get_session()
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == self.job_id).first()
            if job:
                job.processed_urls += processed_inc
                job.indexed_urls += indexed_inc
                job.failed_urls += failed_inc
                if total_override is not None:
                    job.total_urls = total_override
                if final_status:
                    job.status = final_status
                    job.finished_at = datetime.now(timezone.utc)
                if error_msg:
                    job.error_message = error_msg
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to update crawl job %d progress: %s", self.job_id, e)
        finally:
            db.close()

    def run(self) -> Dict[str, Any]:
        """
        Execute the crawl loop:
        1. Enqueue seed URLs.
        2. Claim batches from persistent frontier.
        3. Enforce politeness, robots.txt, network safety.
        4. Fetch, extract, discover links, and incrementally index.
        5. Stop on max pages, completion, or pause/cancel.
        """
        logger.info(
            "Starting crawl job %d with %d seeds (max_pages=%d, max_depth=%d)",
            self.job_id, len(self.seed_urls), self.max_pages, self.max_depth,
        )

        # Mark job as running in DB
        db = self.db_mgr.get_session()
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == self.job_id).first()
            if job:
                job.status = "running"
                db.commit()
        finally:
            db.close()

        # Enqueue seed URLs
        enqueue_stats = self.frontier.enqueue_urls(self.seed_urls, depth=0, priority=10)
        frontier_counts = self.frontier.get_stats()
        self.update_job_progress(total_override=frontier_counts["total_urls"])

        processed_count = 0
        indexed_count = 0
        failed_count = 0

        # Configure HTTP client with strict security limits
        client_kwargs = {
            "timeout": httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0),
            "follow_redirects": True,
            "max_redirects": 5,
            "headers": {"User-Agent": self.robots_mgr.user_agent},
        }

        with httpx.Client(**client_kwargs) as client:
            while processed_count < self.max_pages:
                # 1. Check external control status
                job_status = self.check_job_status()
                if job_status == "paused":
                    logger.info("Crawl job %d paused by operator. Halting loop.", self.job_id)
                    return {"status": "paused", "processed": processed_count, "indexed": indexed_count}
                if job_status in ("cancelled", "failed"):
                    logger.info("Crawl job %d cancelled by operator.", self.job_id)
                    return {"status": "cancelled", "processed": processed_count, "indexed": indexed_count}

                # 2. Claim next batch from frontier
                batch = self.frontier.claim_batch(
                    worker_id=self.worker_id,
                    batch_size=5,
                    lease_seconds=90,
                    allowed_domains=self.allowed_domains if self.allowed_domains else None,
                )

                if not batch:
                    # Nothing currently claimable; check if any retry items exist in the future
                    logger.info("No claimable URLs in frontier for job %d. Crawl complete.", self.job_id)
                    break

                for item in batch:
                    if processed_count >= self.max_pages:
                        break

                    url_id = item["id"]
                    url = item["url"]
                    depth = item["depth"]
                    domain = item["domain"]

                    # 3. Robots.txt check
                    allowed_by_robots, robots_reason = self.robots_mgr.is_allowed(url)
                    if not allowed_by_robots:
                        logger.info("Robots.txt disallowed: %s (%s)", url, robots_reason)
                        self.frontier.mark_skipped(url_id, reason=robots_reason, status=FrontierStatus.BLOCKED)
                        continue

                    # 4. Anti-SSRF and Network Safety check
                    safe_net, sec_reason = validate_url_security(url, check_dns=True)
                    if not safe_net:
                        logger.warning("Network security blocked URL %s: %s", url, sec_reason)
                        self.frontier.mark_skipped(url_id, reason=sec_reason, status=FrontierStatus.SKIPPED_POLICY)
                        continue

                    # 5. Per-host rate limiting
                    wait_sec = self.robots_mgr.get_time_until_next_request(url)
                    if wait_sec > 0:
                        time.sleep(min(wait_sec, 3.0))

                    # 6. Fetch Document
                    try:
                        self.robots_mgr.record_host_access(domain)
                        resp = client.get(url)
                        final_url = str(resp.url)
                        http_status = resp.status_code
                        content_type = resp.headers.get("content-type", "")

                        # Validate redirect destination security
                        if final_url != url:
                            redir_safe, redir_reason = validate_url_security(final_url, check_dns=True)
                            if not redir_safe:
                                self.frontier.mark_skipped(url_id, f"Unsafe redirect: {redir_reason}")
                                continue

                        # Verify response size
                        if len(resp.content) > MAX_RESPONSE_BYTES:
                            self.frontier.mark_failed(
                                url_id,
                                f"Response exceeded max size limit ({len(resp.content)} bytes)",
                                http_status=http_status,
                                is_transient=False,
                            )
                            failed_count += 1
                            self.update_job_progress(failed_inc=1)
                            continue

                        # Check HTTP status
                        if http_status == 200:
                            # Verify content type
                            if not is_allowed_content_type(content_type):
                                self.frontier.mark_skipped(url_id, f"Unsupported content-type: {content_type}")
                                continue

                            # 7. Extract HTML and metadata
                            extracted = self.extractor.extract(
                                html_content=resp.text,
                                url=url,
                                final_url=final_url,
                                http_status=http_status,
                                content_type=content_type,
                            )

                            # 8. Discover links and enqueue into frontier
                            if depth + 1 <= self.max_depth and extracted.outgoing_links:
                                link_stats = self.frontier.enqueue_urls(
                                    extracted.outgoing_links,
                                    parent_url=final_url,
                                    depth=depth + 1,
                                    priority=max(0, 5 - depth),
                                )
                                logger.debug("Discovered %d links from %s", link_stats["discovered"], url)

                            # 9. Deduplicate and index into OpenSearch
                            index_res = self.indexer.process_and_index(extracted, url_id=url_id)
                            self.frontier.mark_fetched(
                                url_id=url_id,
                                http_status=http_status,
                                content_hash=extracted.content_hash,
                                canonical_url=extracted.canonical_url,
                            )

                            processed_count += 1
                            if index_res.get("indexed"):
                                indexed_count += 1
                                self.update_job_progress(processed_inc=1, indexed_inc=1)
                            else:
                                self.update_job_progress(processed_inc=1)

                        elif http_status in (429, 500, 502, 503, 504):
                            # Transient server error or rate limited
                            retry_after = resp.headers.get("retry-after")
                            self.frontier.mark_failed(
                                url_id=url_id,
                                error_message=f"HTTP {http_status}",
                                http_status=http_status,
                                is_transient=True,
                                retry_after_seconds=float(retry_after) if retry_after and retry_after.isdigit() else None,
                            )
                            failed_count += 1
                            self.update_job_progress(failed_inc=1)

                        else:
                            # Permanent client error (404, 403, etc.)
                            self.frontier.mark_failed(
                                url_id=url_id,
                                error_message=f"Permanent HTTP {http_status}",
                                http_status=http_status,
                                is_transient=False,
                            )
                            failed_count += 1
                            self.update_job_progress(failed_inc=1)

                    except httpx.TimeoutException as te:
                        self.frontier.mark_failed(url_id, f"Timeout: {te}", is_transient=True)
                        failed_count += 1
                        self.update_job_progress(failed_inc=1)
                    except httpx.RequestError as re:
                        self.frontier.mark_failed(url_id, f"Network error: {re}", is_transient=True)
                        failed_count += 1
                        self.update_job_progress(failed_inc=1)
                    except Exception as e:
                        logger.exception("Unexpected error crawling %s: %s", url, e)
                        self.frontier.mark_failed(url_id, f"Internal error: {e}", is_transient=False)
                        failed_count += 1
                        self.update_job_progress(failed_inc=1)

                # Update total frontier count
                counts = self.frontier.get_stats()
                self.update_job_progress(total_override=counts["total_urls"])

        # Mark job finished
        self.update_job_progress(final_status="completed")
        logger.info(
            "Crawl job %d completed successfully. Processed: %d, Indexed: %d, Failed: %d",
            self.job_id, processed_count, indexed_count, failed_count,
        )

        return {
            "status": "completed",
            "job_id": self.job_id,
            "processed": processed_count,
            "indexed": indexed_count,
            "failed": failed_count,
        }
