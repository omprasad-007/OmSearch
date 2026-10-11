import json
import logging
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Header, status, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.repositories.database import (
    get_db,
    get_db_manager,
    CrawlJob,
    URLRecord,
    FrontierStatus,
)
from crawler.om_crawler.frontier import FrontierManager
from crawler.om_crawler.crawler_engine import CrawlerEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crawl", tags=["Crawler Management"])

# Active background threads tracked by job_id
ACTIVE_CRAWL_THREADS: Dict[int, threading.Thread] = {}


# --- Request & Response Schemas ---

class CreateCrawlJobRequest(BaseModel):
    seed_urls: List[str] = Field(..., min_length=1, max_length=50, description="List of approved seed URLs to crawl")
    max_pages: int = Field(default=50, ge=1, le=500, description="Maximum total pages to crawl in this job")
    max_depth: int = Field(default=2, ge=0, le=5, description="Maximum link crawl depth")
    allowed_domains: Optional[List[str]] = Field(default=None, description="Optional domain allowlist")
    rate_limit_delay: float = Field(default=1.5, ge=0.5, le=10.0, description="Delay between requests to the same host in seconds")

    @field_validator("seed_urls")
    @classmethod
    def validate_seeds(cls, v: List[str]) -> List[str]:
        cleaned = []
        for url in v:
            u = url.strip()
            if not u.startswith(("http://", "https://")):
                raise ValueError(f"Invalid seed URL scheme (must be http/https): {u}")
            cleaned.append(u)
        return cleaned


class CrawlJobResponse(BaseModel):
    id: int
    job_type: str
    status: str
    total_urls: int
    processed_urls: int
    indexed_urls: int
    failed_urls: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


class CrawlStatsResponse(BaseModel):
    active_jobs: int
    total_urls: int
    total_domains: int
    by_status: Dict[str, int]


class CrawlFailureItem(BaseModel):
    id: int
    url: str
    domain: str
    status: str
    attempt_count: int
    http_status: Optional[int] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None


# --- Background Worker Runner ---

def _run_crawler_background(job_id: int, req: CreateCrawlJobRequest):
    try:
        engine = CrawlerEngine(
            job_id=job_id,
            seed_urls=req.seed_urls,
            max_pages=req.max_pages,
            max_depth=req.max_depth,
            allowed_domains=req.allowed_domains,
            rate_limit_delay=req.rate_limit_delay,
        )
        engine.run()
    except Exception as e:
        logger.exception("Background crawl execution error for job %d: %s", job_id, e)
        db = get_db_manager().get_session()
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
    finally:
        ACTIVE_CRAWL_THREADS.pop(job_id, None)


# --- API Routes ---

@router.post(
    "/jobs",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Crawl Job",
    description="Creates and starts a controlled web crawl job from approved seed URLs.",
)
async def create_crawl_job(
    request: CreateCrawlJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    job = CrawlJob(
        job_type="web_crawl",
        status="running",
        config=json.dumps(request.model_dump()),
        total_urls=len(request.seed_urls),
        processed_urls=0,
        indexed_urls=0,
        failed_urls=0,
        started_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Spawn background crawl thread
    thread = threading.Thread(
        target=_run_crawler_background,
        args=(job.id, request),
        daemon=True,
    )
    ACTIVE_CRAWL_THREADS[job.id] = thread
    thread.start()

    return job


@router.get(
    "/jobs/{job_id}",
    response_model=CrawlJobResponse,
    summary="Get Crawl Job Status",
    description="Returns live status and page progress for a specific crawl job.",
)
async def get_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crawl job with id {job_id} not found",
        )
    return job


@router.get(
    "/stats",
    response_model=CrawlStatsResponse,
    summary="Crawl Frontier Statistics",
    description="Returns aggregate counts of frontier URLs across states.",
)
async def get_crawl_stats():
    frontier = FrontierManager()
    stats = frontier.get_stats()
    active_count = len(ACTIVE_CRAWL_THREADS)
    return CrawlStatsResponse(
        active_jobs=active_count,
        total_urls=stats["total_urls"],
        total_domains=stats["total_domains"],
        by_status=stats["by_status"],
    )


@router.get(
    "/failures",
    response_model=List[CrawlFailureItem],
    summary="Recent Crawl Failures",
    description="Lists recent permanent or transient crawl errors.",
)
async def list_crawl_failures(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = min(max(1, limit), 200)
    failed_records = (
        db.query(URLRecord)
        .filter(URLRecord.status.in_([FrontierStatus.FAILED, FrontierStatus.BLOCKED, FrontierStatus.SKIPPED_POLICY]))
        .order_by(URLRecord.updated_at.desc())
        .limit(limit)
        .all()
    )

    return [
        CrawlFailureItem(
            id=r.id,
            url=r.url,
            domain=r.domain,
            status=r.status,
            attempt_count=r.attempt_count or 0,
            http_status=r.http_status,
            last_error=r.last_error,
            updated_at=r.updated_at,
        )
        for r in failed_records
    ]


@router.post(
    "/jobs/{job_id}/pause",
    summary="Pause Crawl Job",
    description="Temporarily halts processing for the specified job.",
)
async def pause_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "running":
        raise HTTPException(status_code=400, detail=f"Cannot pause job in status '{job.status}'")

    job.status = "paused"
    db.commit()
    return {"message": f"Job {job_id} paused", "status": "paused"}


@router.post(
    "/jobs/{job_id}/resume",
    summary="Resume Crawl Job",
    description="Resumes a paused crawl job.",
)
async def resume_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "paused":
        raise HTTPException(status_code=400, detail=f"Cannot resume job in status '{job.status}'")

    job.status = "running"
    db.commit()

    # Restart worker thread if not already active
    if job_id not in ACTIVE_CRAWL_THREADS and job.config:
        try:
            req_data = json.loads(job.config)
            req = CreateCrawlJobRequest(**req_data)
            thread = threading.Thread(
                target=_run_crawler_background,
                args=(job_id, req),
                daemon=True,
            )
            ACTIVE_CRAWL_THREADS[job_id] = thread
            thread.start()
        except Exception as e:
            logger.error("Failed to restart worker for job %d: %s", job_id, e)

    return {"message": f"Job {job_id} resumed", "status": "running"}


@router.post(
    "/jobs/{job_id}/cancel",
    summary="Cancel Crawl Job",
    description="Permanently terminates an active or paused crawl job.",
)
async def cancel_crawl_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": f"Job {job_id} cancelled", "status": "cancelled"}
