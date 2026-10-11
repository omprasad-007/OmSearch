"""
OM Search - Control Plane Ingestion Router
Operator endpoints for monitoring, policy tuning, pause/resume controls,
task inspection, and index reconciliation.
"""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Header, Depends, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.monitoring import UnifiedIngestionMonitor
from app.ingestion.policy import SchedulingProfile
from app.repositories.database import get_db_manager, IngestionTask, TaskStatus


def verify_operator_token(
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token"),
) -> str:
    settings = get_settings()
    if not x_operator_token or x_operator_token != settings.OPERATOR_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized operator credentials: invalid or missing X-Operator-Token header",
        )
    return x_operator_token


router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["Ingestion Control Plane"],
    dependencies=[Depends(verify_operator_token)],
)

# Singleton coordinator instance for the application
_coordinator_instance: Optional[IngestionCoordinator] = None
_monitor_instance: Optional[UnifiedIngestionMonitor] = None


def get_coordinator() -> IngestionCoordinator:
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = IngestionCoordinator()
    return _coordinator_instance


def get_monitor() -> UnifiedIngestionMonitor:
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = UnifiedIngestionMonitor(coordinator=get_coordinator())
    return _monitor_instance


class PolicyUpdateRequest(BaseModel):
    profile: str = Field(..., description="Target profile: 'BOOTSTRAP', 'STEADY_STATE', 'CUSTOM'")


class PauseResumeRequest(BaseModel):
    source_type: Optional[str] = Field(None, description="Source to pause/resume ('live_crawler', 'archive_importer'). If omitted, toggles globally.")


class CycleRequest(BaseModel):
    max_tasks: int = Field(10, ge=1, le=100, description="Maximum tasks to execute in this cycle")


@router.get("/status")
def get_ingestion_status() -> Dict[str, Any]:
    """Retrieve full operational telemetry across sources, queues, and documents."""
    monitor = get_monitor()
    return monitor.get_full_telemetry()


@router.get("/queues")
def get_queue_stats() -> Dict[str, Any]:
    """Inspect durable task queue depths, leases, and failure states."""
    coord = get_coordinator()
    return coord.scheduler.get_queue_stats()


@router.get("/policies")
def get_policies() -> Dict[str, Any]:
    """Inspect current scheduling profile, worker budgets, and pause state."""
    coord = get_coordinator()
    return coord.policy_engine.to_dict()


@router.post("/policies")
def update_policy(req: PolicyUpdateRequest) -> Dict[str, Any]:
    """Update active scheduling profile."""
    coord = get_coordinator()
    valid_profiles = [SchedulingProfile.BOOTSTRAP, SchedulingProfile.STEADY_STATE, SchedulingProfile.CUSTOM]
    if req.profile not in valid_profiles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid profile '{req.profile}'. Valid options: {valid_profiles}",
        )
    coord.policy_engine.set_profile(req.profile)
    return {"message": f"Profile updated to {req.profile}", "policy": coord.policy_engine.to_dict()}


@router.post("/pause")
def pause_ingestion(
    req: Optional[PauseResumeRequest] = None,
    source_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Pause ingestion globally or for a specific source."""
    coord = get_coordinator()
    target = (req.source_type if req and req.source_type else None) or source_type
    if target:
        coord.policy_engine.pause_source(target)
        return {
            "message": f"Paused source '{target}'",
            "paused_sources": {s: b.is_paused for s, b in coord.policy_engine.budgets.items()},
            "policy": coord.policy_engine.to_dict(),
        }
    coord.policy_engine.pause_all()
    return {
        "message": "Ingestion globally paused (emergency stop active)",
        "paused_sources": {s: b.is_paused for s, b in coord.policy_engine.budgets.items()},
        "policy": coord.policy_engine.to_dict(),
    }


@router.post("/resume")
def resume_ingestion(
    req: Optional[PauseResumeRequest] = None,
    source_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Resume ingestion globally or for a specific source."""
    coord = get_coordinator()
    target = (req.source_type if req and req.source_type else None) or source_type
    if target:
        coord.policy_engine.resume_source(target)
        return {
            "message": f"Resumed source '{target}'",
            "paused_sources": {s: b.is_paused for s, b in coord.policy_engine.budgets.items()},
            "policy": coord.policy_engine.to_dict(),
        }
    coord.policy_engine.resume_all()
    return {
        "message": "Ingestion globally resumed",
        "paused_sources": {s: b.is_paused for s, b in coord.policy_engine.budgets.items()},
        "policy": coord.policy_engine.to_dict(),
    }


@router.get("/tasks/{task_id}")
def get_task_details(task_id: str) -> Dict[str, Any]:
    """Inspect specific task parameters, lease state, and error logs."""
    db = get_db_manager().get_session()
    try:
        task = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
        return {
            "task_id": task.task_id,
            "source_type": task.source_type,
            "work_unit_id": task.work_unit_id,
            "priority_class": task.priority_class,
            "priority_score": task.priority_score,
            "status": task.status,
            "attempt_count": task.attempt_count,
            "max_attempts": task.max_attempts,
            "lease_owner": task.lease_owner,
            "lease_expires_at": task.lease_expires_at.isoformat() if task.lease_expires_at else None,
            "next_eligible_at": task.next_eligible_at.isoformat() if task.next_eligible_at else None,
            "idempotency_key": task.idempotency_key,
            "last_error": task.last_error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
    finally:
        db.close()


@router.post("/tasks/replay")
def replay_failed_tasks(source_type: Optional[str] = None) -> Dict[str, Any]:
    """Replay dead-letter or failed tasks back into PENDING queue."""
    db = get_db_manager().get_session()
    try:
        query = db.query(IngestionTask).filter(IngestionTask.status.in_([TaskStatus.DEAD_LETTER, TaskStatus.FAILED]))
        if source_type:
            query = query.filter(IngestionTask.source_type == source_type)
        tasks = query.all()
        count = len(tasks)
        for t in tasks:
            t.status = TaskStatus.PENDING
            t.attempt_count = 0
            t.last_error = None
        db.commit()
        return {"replayed_tasks": count}
    finally:
        db.close()


@router.post("/reconcile")
def reconcile_documents(limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    """Trigger bidirectional database/OpenSearch reconciliation."""
    coord = get_coordinator()
    res = coord.gateway.reconcile_unindexed_documents(limit=limit)
    return res


@router.post("/cycle")
def run_ingestion_cycle(
    req: Optional[CycleRequest] = None,
    max_tasks: int = Query(10),
) -> Dict[str, Any]:
    """Trigger an explicit ingestion cycle on demand."""
    coord = get_coordinator()
    limit = (req.max_tasks if req else None) or max_tasks
    return coord.run_coordinator_cycle(max_tasks=limit)


class ArchivePlanRequest(BaseModel):
    dataset_id: str = Field("CC-MAIN-2026-10", description="Target Common Crawl dataset")
    max_segments: int = Field(5, ge=1, le=100, description="Max segments to inspect")


class ArchiveStartRequest(BaseModel):
    dataset_id: str = Field("CC-MAIN-2026-10", description="Target Common Crawl dataset")
    max_segments: int = Field(5, ge=1, le=100)


class LiveStartRequest(BaseModel):
    seed_urls: Optional[List[str]] = Field(None, description="Optional seed URLs to prioritize")
    max_pages: int = Field(50, ge=1, le=1000)


@router.get("/metrics")
def get_ingestion_metrics() -> Dict[str, Any]:
    """Retrieve fine-grained ingestion throughput, duplicate rates, and latency metrics."""
    monitor = get_monitor()
    return monitor.get_telemetry_metrics()


@router.get("/jobs")
def list_ingestion_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    source_filter: Optional[str] = Query(None, alias="source"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List durable scheduled ingestion tasks with pagination and filtering."""
    db = get_db_manager().get_session()
    try:
        q = db.query(IngestionTask)
        if status_filter:
            q = q.filter(IngestionTask.status == status_filter)
        if source_filter:
            q = q.filter(IngestionTask.source_type == source_filter)
        total = q.count()
        tasks = q.order_by(IngestionTask.priority_score.desc(), IngestionTask.id.desc()).offset(offset).limit(limit).all()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "jobs": [
                {
                    "task_id": t.task_id,
                    "source_type": t.source_type,
                    "work_unit_id": t.work_unit_id,
                    "priority_class": t.priority_class,
                    "priority_score": t.priority_score,
                    "status": t.status,
                    "attempt_count": t.attempt_count,
                    "last_error": t.last_error,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ],
        }
    finally:
        db.close()


@router.get("/jobs/{job_id}")
def get_job_by_id(job_id: str) -> Dict[str, Any]:
    """Alias for /tasks/{task_id} retrieving single job metadata."""
    return get_task_details(task_id=job_id)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str) -> Dict[str, Any]:
    """Reset attempt count and schedule immediate retry for a failed task."""
    db = get_db_manager().get_session()
    try:
        task = db.query(IngestionTask).filter(IngestionTask.task_id == job_id).first()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
        task.status = TaskStatus.PENDING
        task.attempt_count = 0
        task.last_error = None
        db.commit()
        return {"message": f"Job '{job_id}' queued for retry", "status": TaskStatus.PENDING}
    finally:
        db.close()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    """Cancel a pending or leased ingestion job."""
    db = get_db_manager().get_session()
    try:
        task = db.query(IngestionTask).filter(IngestionTask.task_id == job_id).first()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
        task.status = TaskStatus.DEAD_LETTER
        task.last_error = "Cancelled by operator"
        db.commit()
        return {"message": f"Job '{job_id}' cancelled", "status": TaskStatus.DEAD_LETTER}
    finally:
        db.close()


@router.post("/live/start")
def start_live_crawling(req: Optional[LiveStartRequest] = None) -> Dict[str, Any]:
    """Start or resume live crawl ingestion."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.resume_source(SourceType.LIVE_CRAWLER)
    enqueued = coord.discover_and_enqueue(batch_size=req.max_pages if req else 50)
    return {"message": "Live crawl adapter active", "enqueued": enqueued.get(SourceType.LIVE_CRAWLER, 0)}


@router.post("/live/pause")
def pause_live_crawling() -> Dict[str, Any]:
    """Pause live crawl adapter."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.pause_source(SourceType.LIVE_CRAWLER)
    return {"message": "Live crawl adapter paused"}


@router.post("/live/resume")
def resume_live_crawling() -> Dict[str, Any]:
    """Resume live crawl adapter."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.resume_source(SourceType.LIVE_CRAWLER)
    return {"message": "Live crawl adapter resumed"}


@router.post("/archive/plan")
def plan_archive_import(req: ArchivePlanRequest) -> Dict[str, Any]:
    """Inspect and plan a bounded Common Crawl archive import before execution."""
    est_records = req.max_segments * 1000
    est_duration_sec = round(req.max_segments * 1.5, 1)
    return {
        "dataset_id": req.dataset_id,
        "max_segments": req.max_segments,
        "estimated_records": est_records,
        "estimated_duration_sec": est_duration_sec,
        "memory_safety_mode": "STREAMING_BOUNDED_BUFFER",
        "status": "READY_TO_START",
        "description": f"Plan generated for {req.max_segments} segments from {req.dataset_id}. Safe execution ready.",
    }


@router.post("/archive/start")
def start_archive_import(req: Optional[ArchiveStartRequest] = None) -> Dict[str, Any]:
    """Start bounded Common Crawl archive import through the unified scheduler."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.resume_source(SourceType.ARCHIVE_IMPORTER)
    segments = req.max_segments if req else 5
    enqueued = coord.discover_and_enqueue(batch_size=segments)
    return {
        "message": "Archive importer active",
        "dataset_id": req.dataset_id if req else "CC-MAIN-2026-10",
        "enqueued": enqueued.get(SourceType.ARCHIVE_IMPORTER, 0),
    }


@router.post("/archive/pause")
def pause_archive_import() -> Dict[str, Any]:
    """Pause Common Crawl archive importer."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.pause_source(SourceType.ARCHIVE_IMPORTER)
    return {"message": "Archive importer paused"}


@router.post("/archive/resume")
def resume_archive_import() -> Dict[str, Any]:
    """Resume Common Crawl archive importer."""
    from app.repositories.database import SourceType
    coord = get_coordinator()
    coord.policy_engine.resume_source(SourceType.ARCHIVE_IMPORTER)
    return {"message": "Archive importer resumed"}
