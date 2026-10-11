"""
OM Search - Google Drive Storage Router
Cloud-First page archive management, OAuth 2.0 flow, batch inspection,
and reconciliation endpoints.
"""
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Header, Depends, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from app.core.config import get_settings
from app.services.google_drive_storage import get_google_drive_service
from app.ingestion.drive_batch_pipeline import get_drive_batch_pipeline
from app.repositories.database import get_db_manager, DriveUploadBatch, DriveOAuthCredential
from app.repositories.opensearch_repo import get_opensearch_repo


def verify_operator_token(
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token"),
    token: Optional[str] = Query(None, alias="token"),
) -> str:
    settings = get_settings()
    provided = x_operator_token or token
    if not provided or provided != settings.OPERATOR_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized operator credentials: invalid or missing X-Operator-Token header",
        )
    return provided


router = APIRouter(
    prefix="/api/v1/storage",
    tags=["Storage & Cloud Archive"],
)

# In-memory store for valid OAuth states to prevent CSRF attacks
_active_oauth_states: set = set()


@router.get("/health")
def storage_health() -> Dict[str, Any]:
    """Inspect overall cloud storage health and separation from OpenSearch."""
    gdrive_svc = get_google_drive_service()
    drive_status = gdrive_svc.get_status()
    os_repo = get_opensearch_repo()
    os_healthy = os_repo.ping()

    return {
        "status": "operational",
        "google_drive": {
            "connected": drive_status.get("connected", False),
            "user_email": drive_status.get("user_email"),
            "plan": "Google One 5 TB",
        },
        "opensearch_search_engine": {
            "healthy": os_healthy,
            "engine": "opensearch" if os_healthy else "sqlite_fts5_local",
        },
        "separation_guarantee": "Google Drive is strictly used for durable archives. Search queries query OpenSearch directly without downloading Drive archives.",
    }


@router.get("/google-drive/status")
def google_drive_status(
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Inspect active Google Drive connection, folder hierarchy, and 5 TB quota headroom."""
    gdrive_svc = get_google_drive_service()
    return gdrive_svc.get_status()


@router.get("/google-drive/usage")
def google_drive_usage(
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Detailed breakdown of Google One storage usage, archive batches, and spool."""
    gdrive_svc = get_google_drive_service()
    status_info = gdrive_svc.get_status()
    pipeline = get_drive_batch_pipeline()

    # Calculate spool size on temporary disk
    spool_size = 0
    spool_files = 0
    if pipeline.spool_dir.exists():
        for f in pipeline.spool_dir.glob("*.jsonl.gz"):
            spool_files += 1
            spool_size += f.stat().st_size

    return {
        "connected": status_info.get("connected", False),
        "user_email": status_info.get("user_email"),
        "quota": status_info.get("quota", {}),
        "temporary_local_spool": {
            "spool_dir": str(pipeline.spool_dir),
            "pending_files": spool_files,
            "spool_bytes": spool_size,
        },
        "batch_statistics": status_info.get("batch_statistics", {}),
    }


@router.post("/google-drive/connect")
def google_drive_connect(
    redirect_uri: Optional[str] = Query(None),
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """
    Initiate Google OAuth 2.0 authorization flow.
    Returns consent URL for connecting the operator's Google account with 5 TB plan.
    """
    gdrive_svc = get_google_drive_service()
    try:
        import secrets
        state = secrets.token_urlsafe(32)
        _active_oauth_states.add(state)

        auth_url, _ = gdrive_svc.get_authorization_url(redirect_uri=redirect_uri, state=state)
        return {
            "status": "ready",
            "authorization_url": auth_url,
            "state": state,
            "redirect_uri": redirect_uri or gdrive_svc.settings.GOOGLE_REDIRECT_URI,
            "instructions": "Navigate to authorization_url in browser to grant OM Search access to store page archives.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not initiate Google OAuth: {str(e)}",
        )


@router.get("/google-drive/callback")
def google_drive_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    OAuth 2.0 callback endpoint invoked by Google upon user authorization consent.
    Validates state parameter, exchanges code, initializes OM-Search-Data folders.
    """
    if error:
        return HTMLResponse(
            f"<h2>Google Authorization Error</h2><p>{error}</p>",
            status_code=400,
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code parameter.",
        )

    if state and state not in _active_oauth_states:
        logger.warning("Unrecognized or expired OAuth state parameter: %s", state)

    gdrive_svc = get_google_drive_service()
    try:
        result = gdrive_svc.handle_oauth_callback(code=code, state=state)
        if state in _active_oauth_states:
            _active_oauth_states.remove(state)

        user_email = result.get("user_email", "User")
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Drive Connected - OM Search</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; max-width: 500px; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }}
                .icon {{ font-size: 3rem; margin-bottom: 1rem; color: #10b981; }}
                h2 {{ margin: 0 0 0.5rem 0; color: #38bdf8; font-size: 1.5rem; }}
                p {{ color: #94a3b8; line-height: 1.5; font-size: 0.95rem; }}
                .btn {{ display: inline-block; margin-top: 1.5rem; padding: 0.75rem 1.5rem; background: #0284c7; color: white; border-radius: 0.5rem; text-decoration: none; font-weight: 500; transition: background 0.2s; }}
                .btn:hover {{ background: #0369a1; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">✓</div>
                <h2>Google Drive Connected Successfully!</h2>
                <p>OM Search has linked your Google account (<strong>{user_email}</strong>) and initialized the durable <code>OM-Search-Data</code> folder hierarchy.</p>
                <p>Page archives and manifests will now stream to your cloud storage.</p>
                <a href="/" class="btn">Return to OM Search</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error("OAuth callback processing error: %s", e)
        return HTMLResponse(
            f"<h2>Connection Error</h2><p>{str(e)}</p>",
            status_code=500,
        )


@router.post("/google-drive/disconnect")
def google_drive_disconnect(
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Safely disconnect Google Drive integration and revoke active token."""
    gdrive_svc = get_google_drive_service()
    success = gdrive_svc.disconnect()
    return {"status": "disconnected", "success": success}


@router.get("/batches")
def list_batches(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """List durable archive batches with upload status, record count, and checksums."""
    db = get_db_manager().get_session()
    try:
        q = db.query(DriveUploadBatch)
        if status:
            q = q.filter(DriveUploadBatch.upload_status == status)

        total = q.count()
        batches = (
            q.order_by(DriveUploadBatch.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )

        items = []
        for b in batches:
            items.append({
                "batch_id": b.batch_id,
                "source_type": b.source_type,
                "record_count": b.record_count,
                "uncompressed_bytes": b.uncompressed_bytes,
                "compressed_bytes": b.compressed_bytes,
                "sha256": b.sha256_checksum,
                "upload_status": b.upload_status,
                "drive_file_id": b.drive_file_id,
                "indexing_status": b.indexing_status,
                "uploaded_at": b.uploaded_at.isoformat() if b.uploaded_at else None,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            })

        return {
            "page": page,
            "size": size,
            "total": total,
            "batches": items,
        }
    finally:
        db.close()


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: str,
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Get metadata and status of a specific batch."""
    db = get_db_manager().get_session()
    try:
        b = db.query(DriveUploadBatch).filter(DriveUploadBatch.batch_id == batch_id).first()
        if not b:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found.")

        return {
            "batch_id": b.batch_id,
            "schema_version": b.schema_version,
            "source_type": b.source_type,
            "source_reference": b.source_reference,
            "record_count": b.record_count,
            "uncompressed_bytes": b.uncompressed_bytes,
            "compressed_bytes": b.compressed_bytes,
            "sha256": b.sha256_checksum,
            "upload_status": b.upload_status,
            "drive_file_id": b.drive_file_id,
            "drive_folder_id": b.drive_folder_id,
            "indexing_status": b.indexing_status,
            "attempt_count": b.attempt_count,
            "last_error": b.last_error,
            "uploaded_at": b.uploaded_at.isoformat() if b.uploaded_at else None,
            "indexed_at": b.indexed_at.isoformat() if b.indexed_at else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
    finally:
        db.close()


@router.post("/batches/{batch_id}/retry")
def retry_batch(
    batch_id: str,
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Retry failed upload of an archive batch."""
    pipeline = get_drive_batch_pipeline()
    return pipeline.retry_batch_upload(batch_id)


@router.post("/reconcile")
def reconcile_storage(
    auth: str = Depends(verify_operator_token),
) -> Dict[str, Any]:
    """Reconcile pending storage uploads and unindexed batches."""
    pipeline = get_drive_batch_pipeline()
    return pipeline.reconcile_storage_state()
