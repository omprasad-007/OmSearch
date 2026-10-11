import pytest
import time
from datetime import datetime, timezone, timedelta
from app.repositories.database import (
    get_db_manager,
    IngestionTask,
    TaskStatus,
    TaskPriorityClass,
    SourceType,
)
from app.ingestion.scheduler import DurableTaskScheduler
from app.ingestion.policy import IngestionPolicyEngine, SchedulingProfile


@pytest.fixture
def scheduler():
    db_mgr = get_db_manager()
    s = db_mgr.get_session()
    try:
        s.query(IngestionTask).delete()
        s.commit()
    finally:
        s.close()
    return DurableTaskScheduler()


@pytest.fixture
def policy_engine():
    return IngestionPolicyEngine()


def test_task_idempotency_and_deduplication(scheduler):
    # Enqueue same task key twice
    t1 = scheduler.submit_task(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="https://example.com/idempotent-test",
        priority_class=TaskPriorityClass.ROUTINE,
    )
    t2 = scheduler.submit_task(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="https://example.com/idempotent-test",
        priority_class=TaskPriorityClass.ROUTINE,
    )

    assert t1.task_id == t2.task_id
    assert t1.idempotency_key == t2.idempotency_key


def test_atomic_claim_and_duplicate_claim_prevention(scheduler):
    t = scheduler.submit_task(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="https://example.com/claim-test",
        priority_class=TaskPriorityClass.ROUTINE,
    )

    # Worker 1 claims task
    claimed_w1 = scheduler.claim_next_task(worker_id="worker_alpha", lease_seconds=30)
    assert claimed_w1 is not None
    assert claimed_w1.task_id == t.task_id
    assert claimed_w1.status == TaskStatus.LEASED

    # Worker 2 attempts to claim - queue should be empty or different task
    claimed_w2 = scheduler.claim_next_task(worker_id="worker_beta", lease_seconds=30)
    assert claimed_w2 is None or claimed_w2.task_id != t.task_id

    # Worker 1 completes the task
    scheduler.complete_task(task_id=t.task_id)
    db = get_db_manager().get_session()
    try:
        task_db = db.query(IngestionTask).filter_by(task_id=t.task_id).first()
        assert task_db.status == TaskStatus.COMPLETED
    finally:
        db.close()


def test_lease_expiration_and_recovery(scheduler):
    t = scheduler.submit_task(
        source_type=SourceType.ARCHIVE_IMPORTER,
        work_unit_id="archive_partition_expired_lease",
        priority_class=TaskPriorityClass.BULK_ARCHIVE,
    )

    # Claim with short lease (1 second)
    claimed = scheduler.claim_next_task(worker_id="crashed_worker", lease_seconds=1)
    assert claimed is not None
    assert claimed.task_id == t.task_id

    # Wait for lease to expire
    time.sleep(1.2)

    # Reclaim expired leases
    recovered_count = scheduler.reclaim_expired_leases()
    assert recovered_count >= 1

    # Another worker can now claim the task
    new_claimed = scheduler.claim_next_task(worker_id="recovery_worker", lease_seconds=30)
    assert new_claimed is not None
    assert new_claimed.task_id == t.task_id

    scheduler.complete_task(new_claimed.task_id)


def test_priority_ordering_and_queue_aging(scheduler):
    # Enqueue Bulk Archive task first
    bulk_task = scheduler.submit_task(
        source_type=SourceType.ARCHIVE_IMPORTER,
        work_unit_id="bulk_aging_test",
        priority_class=TaskPriorityClass.BULK_ARCHIVE,
    )

    # Enqueue Urgent task
    urgent_task = scheduler.submit_task(
        source_type=SourceType.LIVE_CRAWLER,
        work_unit_id="urgent_update_test",
        priority_class=TaskPriorityClass.URGENT,
    )

    # Urgent should be claimed before bulk
    claimed = scheduler.claim_next_task(worker_id="priority_worker")
    assert claimed is not None
    assert claimed.task_id == urgent_task.task_id
    scheduler.complete_task(urgent_task.task_id)

    # Next claim should get bulk
    claimed_bulk = scheduler.claim_next_task(worker_id="priority_worker")
    assert claimed_bulk is not None
    assert claimed_bulk.task_id == bulk_task.task_id
    scheduler.complete_task(bulk_task.task_id)


def test_policy_engine_pause_resume_and_emergency_stop(policy_engine):
    # Initial state: active
    assert policy_engine.is_source_runnable(SourceType.LIVE_CRAWLER) is True
    assert policy_engine.is_source_runnable(SourceType.ARCHIVE_IMPORTER) is True

    # Pause archive only
    policy_engine.pause_source(SourceType.ARCHIVE_IMPORTER)
    assert policy_engine.is_source_runnable(SourceType.LIVE_CRAWLER) is True
    assert policy_engine.is_source_runnable(SourceType.ARCHIVE_IMPORTER) is False

    # Resume archive
    policy_engine.resume_source(SourceType.ARCHIVE_IMPORTER)
    assert policy_engine.is_source_runnable(SourceType.ARCHIVE_IMPORTER) is True

    # Global emergency stop
    policy_engine.pause_all()
    assert policy_engine.is_source_runnable(SourceType.LIVE_CRAWLER) is False
    assert policy_engine.is_source_runnable(SourceType.ARCHIVE_IMPORTER) is False

    # Clear emergency stop
    policy_engine.resume_all()
    assert policy_engine.is_source_runnable(SourceType.LIVE_CRAWLER) is True
    assert policy_engine.is_source_runnable(SourceType.ARCHIVE_IMPORTER) is True


def test_scheduling_profiles_budget_allocation(policy_engine):
    # Test BOOTSTRAP profile favors archive
    policy_engine.set_profile(SchedulingProfile.BOOTSTRAP)
    assert policy_engine.budgets["archive_importer"].max_workers > policy_engine.budgets["live_crawler"].max_workers
    assert policy_engine.budgets["live_crawler"].reserved_min_workers >= 1

    # Test STEADY_STATE profile favors live crawler
    policy_engine.set_profile(SchedulingProfile.STEADY_STATE)
    assert policy_engine.budgets["live_crawler"].max_workers > policy_engine.budgets["archive_importer"].max_workers
    assert policy_engine.budgets["archive_importer"].reserved_min_workers >= 1
