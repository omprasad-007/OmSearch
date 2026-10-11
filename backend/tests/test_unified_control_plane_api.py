import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def operator_headers():
    settings = get_settings()
    return {"X-Operator-Token": settings.OPERATOR_API_KEY}


def test_unauthorized_access_rejected(client):
    # Missing token
    resp = client.get("/api/v1/ingestion/status")
    assert resp.status_code == 401

    # Wrong token
    resp = client.get("/api/v1/ingestion/status", headers={"X-Operator-Token": "bad_token"})
    assert resp.status_code == 401


def test_status_endpoint(client, operator_headers):
    resp = client.get("/api/v1/ingestion/status", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "documents" in data
    assert "queues" in data


def test_queues_endpoint(client, operator_headers):
    resp = client.get("/api/v1/ingestion/queues", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tasks" in data
    assert "pending" in data


def test_policies_and_pause_resume(client, operator_headers):
    # View policy
    resp = client.get("/api/v1/ingestion/policies", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "profile" in data

    # Pause bulk archive source
    resp_pause = client.post(
        "/api/v1/ingestion/pause",
        params={"source_type": "archive_importer"},
        headers=operator_headers,
    )
    assert resp_pause.status_code == 200
    assert resp_pause.json()["paused_sources"]["archive_importer"] is True

    # Resume bulk archive source
    resp_resume = client.post(
        "/api/v1/ingestion/resume",
        params={"source_type": "archive_importer"},
        headers=operator_headers,
    )
    assert resp_resume.status_code == 200
    assert resp_resume.json()["paused_sources"]["archive_importer"] is False


def test_reconciliation_endpoint(client, operator_headers):
    resp = client.post(
        "/api/v1/ingestion/reconcile",
        params={"limit": 10},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reconciled" in data


def test_metrics_endpoint(client, operator_headers):
    resp = client.get("/api/v1/ingestion/metrics", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "queue_depth_total" in data
    assert "priority_classes" in data
    assert "backpressure_state" in data


def test_jobs_list_and_details(client, operator_headers):
    resp = client.get("/api/v1/ingestion/jobs?limit=10", headers=operator_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_archive_plan_and_controls(client, operator_headers):
    # Plan
    plan_resp = client.post(
        "/api/v1/ingestion/archive/plan",
        json={"dataset_id": "CC-MAIN-2026-10", "max_segments": 3},
        headers=operator_headers,
    )
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["status"] == "READY_TO_START"
    assert plan_data["estimated_records"] == 3000

    # Start
    start_resp = client.post(
        "/api/v1/ingestion/archive/start",
        json={"dataset_id": "CC-MAIN-2026-10", "max_segments": 2},
        headers=operator_headers,
    )
    assert start_resp.status_code == 200
    assert "Archive importer active" in start_resp.json()["message"]

    # Pause
    pause_resp = client.post("/api/v1/ingestion/archive/pause", headers=operator_headers)
    assert pause_resp.status_code == 200
    assert "paused" in pause_resp.json()["message"]


def test_live_controls(client, operator_headers):
    # Start live
    start_resp = client.post(
        "/api/v1/ingestion/live/start",
        json={"max_pages": 10},
        headers=operator_headers,
    )
    assert start_resp.status_code == 200
    assert "Live crawl adapter active" in start_resp.json()["message"]

    # Pause live
    pause_resp = client.post("/api/v1/ingestion/live/pause", headers=operator_headers)
    assert pause_resp.status_code == 200
    assert "paused" in pause_resp.json()["message"]

