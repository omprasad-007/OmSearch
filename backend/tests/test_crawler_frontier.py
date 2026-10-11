import uuid
from datetime import datetime, timezone, timedelta
from crawler.om_crawler.frontier import FrontierManager
from app.repositories.database import FrontierStatus, URLRecord, get_db_manager


def test_frontier_enqueue_and_deduplication():
    frontier = FrontierManager()
    uid = uuid.uuid4().hex[:6]
    urls = [
        f"https://test-site-{uid}.org/page1",
        f"https://test-site-{uid}.org/page1",            # Exact duplicate
        f"https://test-site-{uid}.org/page1?utm_source=x", # Normalized duplicate
        f"https://test-site-{uid}.org/page2",
    ]

    stats = frontier.enqueue_urls(urls, depth=0, priority=5)
    assert stats["discovered"] == 2
    assert stats["duplicates"] == 2


def test_frontier_claim_batch_and_lease():
    frontier = FrontierManager()
    uid = uuid.uuid4().hex[:6]
    frontier.enqueue_urls([f"https://claim-{uid}.org/item1", f"https://claim-{uid}.org/item2"], depth=0)

    # Worker 1 claims batch
    claimed = frontier.claim_batch(worker_id=f"worker-{uid}", batch_size=5, allowed_domains=[f"claim-{uid}.org"])
    assert len(claimed) >= 1

    first_item = claimed[0]
    assert first_item["attempt_count"] >= 1


def test_frontier_reset_expired_leases():
    frontier = FrontierManager()
    db = get_db_manager().get_session()
    uid = uuid.uuid4().hex[:6]
    test_url = f"https://expired-{uid}.org/lost"
    try:
        # Create a record that has an expired lease
        past_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        rec = URLRecord(
            url=test_url,
            normalized_url=test_url,
            canonical_url=test_url,
            domain=f"expired-{uid}.org",
            status=FrontierStatus.FETCHING,
            worker_id="dead-worker",
            lease_expires_at=past_time,
        )
        db.add(rec)
        db.commit()
    finally:
        db.close()

    # Reclaim leases
    reclaimed = frontier.reset_expired_leases()
    assert reclaimed >= 1

    # Verify status reverted to QUEUED
    db = get_db_manager().get_session()
    try:
        reclaimed_rec = db.query(URLRecord).filter(URLRecord.url == test_url).first()
        assert reclaimed_rec.status == FrontierStatus.QUEUED
        assert reclaimed_rec.worker_id is None
    finally:
        db.close()


def test_frontier_exponential_backoff_retry():
    frontier = FrontierManager()
    uid = uuid.uuid4().hex[:6]
    retry_url = f"https://retry-{uid}.org/transient-error"
    frontier.enqueue_urls([retry_url], depth=0)
    claimed = frontier.claim_batch(worker_id=f"worker-{uid}", batch_size=1, allowed_domains=[f"retry-{uid}.org"])
    assert len(claimed) == 1
    url_id = claimed[0]["id"]

    # Mark as transient failure
    frontier.mark_failed(url_id, error_message="HTTP 503 Service Unavailable", http_status=503, is_transient=True)

    db = get_db_manager().get_session()
    try:
        rec = db.query(URLRecord).filter(URLRecord.id == url_id).first()
        assert rec.status == FrontierStatus.RETRY_WAIT
        assert rec.next_fetch_at is not None
        assert rec.attempt_count == 1
    finally:
        db.close()
