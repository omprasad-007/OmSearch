from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.repositories.database import get_db_manager, CrawlJob

client = TestClient(app)


def test_crawl_api_create_job_and_get_status():
    payload = {
        "seed_urls": ["https://example.com/seed-1", "https://example.com/seed-2"],
        "max_pages": 10,
        "max_depth": 2,
        "rate_limit_delay": 1.0,
    }
    with patch("app.api.v1.crawl_router._run_crawler_background"):
        response = client.post("/api/v1/crawl/jobs", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["job_type"] == "web_crawl"
    job_id = data["id"]

    # Get status
    get_resp = client.get(f"/api/v1/crawl/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id


def test_crawl_api_pause_resume_cancel():
    db = get_db_manager().get_session()
    try:
        job = CrawlJob(
            job_type="web_crawl",
            status="running",
            config='{"seed_urls": ["https://example.com"], "max_pages": 5, "max_depth": 1}',
            total_urls=1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    # Pause
    pause_resp = client.post(f"/api/v1/crawl/jobs/{job_id}/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # Resume
    resume_resp = client.post(f"/api/v1/crawl/jobs/{job_id}/resume")
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "running"

    # Cancel
    cancel_resp = client.post(f"/api/v1/crawl/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_crawl_api_stats():
    resp = client.get("/api/v1/crawl/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_urls" in data
    assert "by_status" in data


def test_crawl_api_failures():
    resp = client.get("/api/v1/crawl/failures")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
