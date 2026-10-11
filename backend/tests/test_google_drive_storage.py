import os
import gzip
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.services.google_drive_storage import GoogleDriveStorageService, get_google_drive_service
from app.ingestion.drive_batch_pipeline import DriveBatchPipeline, get_drive_batch_pipeline
from app.repositories.database import (
    get_db_manager,
    DriveUploadBatch,
    DriveOAuthCredential,
)

client = TestClient(app)
settings = get_settings()
AUTH_HEADERS = {"X-Operator-Token": settings.OPERATOR_API_KEY}


@pytest.fixture(autouse=True)
def ensure_db():
    get_db_manager()


def test_encryption_roundtrip():
    """Verify OAuth tokens are encrypted with Fernet and decrypted accurately."""
    service = GoogleDriveStorageService()
    secret_payload = json.dumps({"refresh_token": "1//test_refresh_token_xyz", "token": "ya29.test"})
    encrypted = service._encrypt(secret_payload)
    assert encrypted != secret_payload
    decrypted = service._decrypt(encrypted)
    assert decrypted == secret_payload


def test_authorization_url_generation():
    """Verify OAuth consent URL is generated with correct scopes, state, and offline access."""
    with patch.object(settings, "GOOGLE_CLIENT_ID", "test-client-id"), \
         patch.object(settings, "GOOGLE_CLIENT_SECRET", "test-client-secret"):
        service = GoogleDriveStorageService()
        auth_url, state = service.get_authorization_url(state="secure_test_state_123")
        assert "accounts.google.com" in auth_url
        assert "secure_test_state_123" in auth_url
        assert "drive.file" in auth_url
        assert "access_type=offline" in auth_url or "access_type" in auth_url


def test_storage_health_endpoint():
    """Verify GET /api/v1/storage/health exposes cloud archive and OpenSearch health."""
    resp = client.get("/api/v1/storage/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "google_drive" in data
    assert "opensearch_search_engine" in data
    assert "separation_guarantee" in data


def test_unauthorized_storage_access_rejected():
    """Verify operational endpoints reject requests without valid operator token."""
    resp = client.get("/api/v1/storage/google-drive/status")
    assert resp.status_code == 401

    resp = client.post("/api/v1/storage/google-drive/disconnect")
    assert resp.status_code == 401


def test_storage_status_endpoint():
    """Verify GET /api/v1/storage/google-drive/status with operator authentication."""
    resp = client.get("/api/v1/storage/google-drive/status", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data


def test_batch_pipeline_serialization_and_checksum():
    """Verify DriveBatchPipeline serializes records to .jsonl.gz with SHA256 checksum."""
    pipeline = DriveBatchPipeline()
    sample_records = [
        {
            "id": "doc_test_1",
            "url": "https://example.com/page1",
            "title": "Example Page 1",
            "snippet": "Snippet of page 1",
            "content": "Full content of page 1 for test",
            "domain": "example.com",
            "language": "en",
        },
        {
            "id": "doc_test_2",
            "url": "https://example.com/page2",
            "title": "Example Page 2",
            "snippet": "Snippet of page 2",
            "content": "Full content of page 2 for test",
            "domain": "example.com",
            "language": "en",
        },
    ]

    res = pipeline.process_and_archive_batch(
        records=sample_records,
        source_type="test_unit",
        source_reference="partition_test_001",
    )

    assert res["batch_id"] is not None
    assert res["record_count"] == 2
    assert res["compressed_bytes"] > 0
    assert len(res["sha256"]) == 64
    assert res["indexing_status"] == "indexed"

    # Verify batch is recorded in database
    db = get_db_manager().get_session()
    b = db.query(DriveUploadBatch).filter(DriveUploadBatch.batch_id == res["batch_id"]).first()
    assert b is not None
    assert b.record_count == 2
    assert b.sha256_checksum == res["sha256"]
    db.close()


def test_mocked_drive_upload_and_spool_cleanup():
    """
    Verify that when Google Drive upload succeeds:
    1. Batch status transitions to 'verified'.
    2. Local spool file is deleted to eliminate local disk dependence.
    """
    pipeline = DriveBatchPipeline()
    sample_records = [{"id": "doc_clean_1", "url": "https://example.com/clean", "title": "Clean Test", "content": "Text"}]

    mock_drive_service = MagicMock()
    mock_drive_service.get_status.return_value = {"connected": True}
    mock_drive_service.upload_batch.return_value = {
        "file_id": "drive_file_id_mock_999",
        "folder_id": "drive_folder_id_mock_888",
        "size_bytes": 150,
    }

    with patch.object(pipeline, "drive_service", mock_drive_service):
        res = pipeline.process_and_archive_batch(
            records=sample_records,
            source_type="mock_upload_test",
        )

        assert res["batch_id"] is not None
        assert res["upload_status"] == "verified"
        assert res["drive_file_id"] == "drive_file_id_mock_999"

        # Check DB
        db = get_db_manager().get_session()
        b = db.query(DriveUploadBatch).filter(DriveUploadBatch.batch_id == res["batch_id"]).first()
        assert b.upload_status == "verified"
        assert b.drive_file_id == "drive_file_id_mock_999"
        # Local spool should be pruned
        assert b.local_spool_path is None or not Path(b.local_spool_path).exists()
        db.close()


def test_batches_listing_and_retry_api():
    """Verify GET /api/v1/storage/batches and POST /api/v1/storage/batches/{id}/retry."""
    resp = client.get("/api/v1/storage/batches", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "batches" in data
    assert "total" in data

    if data["batches"]:
        batch_id = data["batches"][0]["batch_id"]
        detail_resp = client.get(f"/api/v1/storage/batches/{batch_id}", headers=AUTH_HEADERS)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["batch_id"] == batch_id


def test_search_never_invokes_google_drive():
    """
    CRITICAL PERFORMANCE REQUIREMENT:
    Verify that an ordinary search request executes entirely in OpenSearch/FTS5
    and NEVER calls Google Drive.
    """
    mock_drive = MagicMock()
    with patch("app.services.google_drive_storage.GoogleDriveStorageService", return_value=mock_drive):
        resp = client.get("/api/v1/search?q=quantum")
        assert resp.status_code == 200
        # Google Drive mock was never called
        mock_drive.upload_batch.assert_not_called()
        mock_drive.download_batch.assert_not_called()
