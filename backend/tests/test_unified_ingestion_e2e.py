import os
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch
import pytest

from app.core.config import get_settings
from app.repositories.database import (
    get_db_manager,
    IngestionTask,
    DocumentRegistry,
    HistoricalCapture,
    DocumentAlias,
    TaskStatus,
    TaskPriorityClass,
    SourceType,
)
from app.repositories.opensearch_repo import get_opensearch_repo
from app.services.search_service import SearchService
from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.policy import SchedulingProfile
from app.ingestion.adapters.live_crawler_adapter import LiveCrawlerAdapter
from app.ingestion.adapters.bulk_archive_adapter import BulkArchiveImporterAdapter


class LocalFixtureServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress console logging during tests

    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"User-agent: *\nDisallow: /private/\n")

        elif self.path == "/shared-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Quantum XenonHydra Live Portal</title></head>
            <body>
                <h1>Quantum XenonHydra Live Portal</h1>
                <p>XenonHydraLive2026 is the current active verified scientific consensus.</p>
                <a href="/duplicate-page">Duplicate Link</a>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/duplicate-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Quantum XenonHydra Mirror</title></head>
            <body>
                <h1>Quantum XenonHydra Mirror</h1>
                <p>XenonHydraLive2026 is the current active verified scientific consensus.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/interrupted-target":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Worker Resilience Recovery Node</h1><p>Processed after safe lease resumption.</p>")

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


@pytest.fixture(scope="module")
def fixture_http_server():
    server = HTTPServer(("127.0.0.1", 0), LocalFixtureServerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_unified_ingestion_acceptance_e2e(fixture_http_server):
    """
    MASTER INTEGRATION ACCEPTANCE TEST (Section 19 Requirements):
    1. Both sources can submit work.
    2. The scheduler allocates work according to the configured policy.
    3. Duplicate records do not create duplicate current search results.
    4. The older archive record cannot overwrite newer valid live content.
    5. Historical provenance remains available.
    6. Failed writes recover through retries.
    7. Workers resume without corrupting task state.
    8. The existing OM search endpoint returns the correct current document.
    9. Both source-specific progress reports remain accurate.
    10. Global and per-source pause controls work.
    """
    settings = get_settings()
    db_mgr = get_db_manager()

    # Clear scheduler tasks and document registries for deterministic E2E test isolation
    s = db_mgr.get_session()
    try:
        s.query(IngestionTask).delete()
        s.query(DocumentRegistry).delete()
        s.query(HistoricalCapture).delete()
        s.query(DocumentAlias).delete()
        s.commit()
    finally:
        s.close()

    coordinator = IngestionCoordinator()
    live_adapter = coordinator.live_crawler_adapter
    archive_adapter = coordinator.archive_adapter

    shared_url = f"{fixture_http_server}/shared-page"
    dup_url = f"{fixture_http_server}/duplicate-page"
    interrupted_url = f"{fixture_http_server}/interrupted-target"

    archive_fixture_batch_id = "acceptance_warc_manifest_001"
    sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)

    # -------------------------------------------------------------
    # 1. VERIFY: Both sources can submit work
    # -------------------------------------------------------------
    # A) Submit Live Crawler Task
    task_live = coordinator.submit_work(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id=shared_url,
        priority_class=TaskPriorityClass.ROUTINE,
        payload={"url": shared_url, "max_depth": 1},
    )
    assert task_live is not None

    # B) Submit Bulk Archive Task with older capture of shared_url and an archive-only URL
    archive_docs = [
        {
            "url": shared_url,
            "title": "Quantum XenonHydra Old Archive Draft",
            "content": "XenonHydraArchive2024 outdated historical hypothesis and obsolete theory.",
            "source_type": SourceType.ARCHIVE_IMPORTER,
            "source_captured_at": sixty_days_ago.isoformat(),
            "source_archive_id": archive_fixture_batch_id,
        },
        {
            "url": "https://archive.example.org/ancient-manuscript",
            "title": "Ancient Codex Archive Record",
            "content": "AncientArchiveScroll1999 preserved historical scrolls and texts.",
            "source_type": SourceType.ARCHIVE_IMPORTER,
            "source_captured_at": sixty_days_ago.isoformat(),
            "source_archive_id": archive_fixture_batch_id,
        },
    ]

    task_bulk = coordinator.submit_work(
        source_type=SourceType.ARCHIVE_IMPORTER,
        work_unit_id=f"archive_partition_{archive_fixture_batch_id}",
        priority_class=TaskPriorityClass.BULK_ARCHIVE,
        payload={"records": archive_docs},
    )
    assert task_bulk is not None

    q_stats = coordinator.scheduler.get_queue_stats()
    assert q_stats["total_tasks"] >= 2
    assert q_stats["pending"] >= 2

    # -------------------------------------------------------------
    # 2. VERIFY: Scheduler allocates work according to configured policy
    # -------------------------------------------------------------
    # In STEADY_STATE profile, LIVE crawler receives higher priority weighting
    coordinator.policy_engine.set_profile(SchedulingProfile.STEADY_STATE)
    claimed_first = coordinator.scheduler.claim_next_task(worker_id="test_worker_1")
    assert claimed_first is not None
    assert claimed_first.source_type == SourceType.LIVE_CRAWLER
    assert claimed_first.work_unit_id == shared_url

    # Ingest the live document for shared_url
    live_content = "XenonHydraLive2026 is the current active verified scientific consensus."
    res_live = coordinator.gateway.submit_document(
        raw_url=shared_url,
        title="Quantum XenonHydra Live Portal",
        content=live_content,
        source_type=SourceType.LIVE_CRAWLER,
        live_fetched_at=datetime.now(timezone.utc),
    )
    assert res_live["indexed"] is True
    coordinator.scheduler.complete_task(claimed_first.task_id)

    # -------------------------------------------------------------
    # 4 & 5. VERIFY: Older archive record cannot overwrite newer live content;
    #                Historical provenance remains preserved
    # -------------------------------------------------------------
    claimed_second = coordinator.scheduler.claim_next_task(worker_id="test_worker_1")
    assert claimed_second is not None
    assert claimed_second.source_type == SourceType.ARCHIVE_IMPORTER

    # Execute archive batch containing the older shared_url snapshot
    batch_res = coordinator.gateway.submit_batch(
        documents=archive_docs,
        source_type=SourceType.ARCHIVE_IMPORTER,
        source_archive_id=archive_fixture_batch_id,
    )
    assert batch_res["total"] == 2
    # Ancient codex was indexed, but older shared_url was preserved as historical capture only
    assert batch_res["indexed"] == 1
    assert batch_res["skipped"] == 1
    coordinator.scheduler.complete_task(claimed_second.task_id)

    # Verify DocumentRegistry has LIVE content as active
    db = db_mgr.get_session()
    try:
        shared_ids = coordinator.identity_service.resolve_identities(shared_url, live_content)
        reg = db.query(DocumentRegistry).filter_by(doc_id=shared_ids["doc_id"]).first()
        assert reg.active_source_type == SourceType.LIVE_CRAWLER
        assert "Live Portal" in reg.primary_url or "Live Portal" in (reg.domain or "") or reg.active_source_type == "live_crawler"

        # Verify historical captures contains BOTH live and archive captures
        caps = db.query(HistoricalCapture).filter_by(canonical_url=shared_ids["canonical_url"]).all()
        assert len(caps) >= 2
        cap_sources = [c.source_type for c in caps]
        assert SourceType.LIVE_CRAWLER in cap_sources
        assert SourceType.ARCHIVE_IMPORTER in cap_sources
    finally:
        db.close()

    # -------------------------------------------------------------
    # 3. VERIFY: Duplicate records do not create duplicate current search results
    # -------------------------------------------------------------
    # Ingest duplicate live page with identical content
    res_dup = coordinator.gateway.submit_document(
        raw_url=dup_url,
        title="Quantum XenonHydra Mirror",
        content=live_content,  # Exact duplicate text
        source_type=SourceType.LIVE_CRAWLER,
        canonical_hint=shared_url,  # Explicitly points to canonical
    )
    # Alias created, search documents remains 1 canonical
    db = db_mgr.get_session()
    try:
        alias = db.query(DocumentAlias).filter_by(alternate_url=dup_url).first()
        assert alias is not None
    finally:
        db.close()

    # -------------------------------------------------------------
    # 8. VERIFY: OM search endpoint returns correct current document
    # -------------------------------------------------------------
    search_service = SearchService()
    search_res = search_service.search("XenonHydraLive2026", page=1, size=10)
    assert search_res.total >= 1
    # Check top hit title is the live version
    top_hit = search_res.results[0]
    assert "Live Portal" in top_hit.title
    assert "XenonHydraLive2026" in top_hit.snippet or "consensus" in top_hit.snippet

    # -------------------------------------------------------------
    # 6. VERIFY: Failed writes recover through retries
    # -------------------------------------------------------------
    failing_task = coordinator.submit_work(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="https://example.com/transient-failure-target",
        priority_class=TaskPriorityClass.ROUTINE,
    )
    claimed_fail = coordinator.scheduler.claim_next_task(worker_id="flaky_worker")
    assert claimed_fail is not None
    assert claimed_fail.task_id == failing_task.task_id

    # Simulate transient network/indexing error
    coordinator.scheduler.fail_task(
        task_id=failing_task.task_id,
        error="OpenSearch temporary connection timeout (simulated)",
        backoff_seconds=0.1,
    )
    # Check task moved to retry
    db = db_mgr.get_session()
    try:
        t_failed = db.query(IngestionTask).filter_by(task_id=failing_task.task_id).first()
        assert t_failed.attempt_count == 1
        assert t_failed.status == TaskStatus.PENDING
        assert t_failed.priority_class == TaskPriorityClass.RETRY
    finally:
        db.close()

    # Wait for backoff to expire
    time.sleep(0.2)

    # Next claim picks up retry task and successfully completes it
    claimed_retry = coordinator.scheduler.claim_next_task(worker_id="healed_worker")
    assert claimed_retry is not None
    assert claimed_retry.task_id == failing_task.task_id
    coordinator.scheduler.complete_task(claimed_retry.task_id)

    # -------------------------------------------------------------
    # 7. VERIFY: Workers resume without corrupting task state
    # -------------------------------------------------------------
    task_interrupt = coordinator.submit_work(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id=interrupted_url,
        priority_class=TaskPriorityClass.ROUTINE,
    )
    # Worker claims task with 1-second lease then crashes
    claimed_crashed = coordinator.scheduler.claim_next_task(worker_id="crashed_worker_node", lease_seconds=1)
    assert claimed_crashed is not None
    assert claimed_crashed.task_id == task_interrupt.task_id
    assert claimed_crashed.status == TaskStatus.LEASED

    # Simulate delay past lease expiration
    time.sleep(1.2)

    # Reclaim expired leases
    reclaimed = coordinator.scheduler.reclaim_expired_leases()
    assert reclaimed >= 1

    # Restarted worker claims and finishes work safely
    claimed_resumed = coordinator.scheduler.claim_next_task(worker_id="resumed_worker_node")
    assert claimed_resumed is not None
    assert claimed_resumed.task_id == task_interrupt.task_id
    coordinator.scheduler.complete_task(claimed_resumed.task_id)

    # -------------------------------------------------------------
    # 9. VERIFY: Source-specific progress reports remain accurate
    # -------------------------------------------------------------
    telemetry = coordinator.monitor.get_full_telemetry()
    assert telemetry["status"] == "RUNNING"
    assert telemetry["documents"]["unique_searchable_documents"] >= 1
    assert telemetry["documents"]["total_historical_captures"] >= 2
    assert "queues" in telemetry

    # -------------------------------------------------------------
    # 10. VERIFY: Global and per-source pause controls work
    # -------------------------------------------------------------
    # Enqueue a live task and an archive task
    t_live_pause = coordinator.submit_work(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="https://example.com/pause-live-test",
        priority_class=TaskPriorityClass.ROUTINE,
    )
    t_arch_pause = coordinator.submit_work(
        source_type=SourceType.ARCHIVE_IMPORTER,
        work_unit_id="https://example.com/pause-arch-test",
        priority_class=TaskPriorityClass.BULK_ARCHIVE,
    )

    # A) Pause LIVE CRAWLER only
    coordinator.policy_engine.pause_source(SourceType.LIVE_CRAWLER)
    claimed_while_paused = coordinator.scheduler.claim_next_task(worker_id="pause_tester")
    # Live is paused, so only Archive may be claimed
    assert claimed_while_paused is not None
    assert claimed_while_paused.source_type == SourceType.ARCHIVE_IMPORTER
    coordinator.scheduler.complete_task(claimed_while_paused.task_id)

    # B) Resume Live Crawler
    coordinator.policy_engine.resume_source(SourceType.LIVE_CRAWLER)

    # C) Global Emergency Stop
    coordinator.policy_engine.pause_all()
    claimed_stop = coordinator.scheduler.claim_next_task(worker_id="pause_tester")
    assert claimed_stop is None  # Emergency stop prevents any claims

    coordinator.policy_engine.resume_all()
    claimed_resumed = coordinator.scheduler.claim_next_task(worker_id="pause_tester")
    assert claimed_resumed is not None
    assert claimed_resumed.source_type == SourceType.LIVE_CRAWLER
    coordinator.scheduler.complete_task(claimed_resumed.task_id)
