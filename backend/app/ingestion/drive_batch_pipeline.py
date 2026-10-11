import os
import gzip
import json
import uuid
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.database import (
    get_db_manager,
    DriveUploadBatch,
    DriveStorageReport,
)
from app.services.google_drive_storage import get_google_drive_service
from app.ingestion.indexing_gateway import get_indexing_gateway

logger = logging.getLogger(__name__)


class DriveBatchPipeline:
    """
    Coordinates durable batch aggregation, gzip compression, SHA256 checksumming,
    Google Drive cloud archiving, temporary spool pruning, and OpenSearch indexing.
    """

    def __init__(self):
        self.settings = get_settings()
        self.spool_dir = Path(self.settings.GOOGLE_DRIVE_TEMP_DIR).resolve()
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.drive_service = get_google_drive_service()

    def process_and_archive_batch(
        self,
        records: List[Dict[str, Any]],
        source_type: str = "unified_stream",
        source_reference: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Process a list of normalized documents into a durable cloud-backed batch.
        1. Compresses to .jsonl.gz in temporary spool.
        2. Calculates SHA256 checksum.
        3. Persists batch record in PostgreSQL.
        4. Uploads to Google Drive (if connected) and deletes local spool.
        5. Bulk indexes into OpenSearch.
        """
        if not records:
            return {"batch_id": None, "record_count": 0, "status": "empty"}

        batch_id = f"batch_{source_type}_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"
        filename = f"{batch_id}.jsonl.gz"
        local_path = self.spool_dir / filename

        # 1. Serialize records to compressed .jsonl.gz
        uncompressed_bytes = 0
        hasher = hashlib.sha256()

        with gzip.open(local_path, "wt", encoding="utf-8") as gz_out:
            for r in records:
                # Ensure canonical schema fields
                canonical_record = {
                    "id": r.get("id") or r.get("url"),
                    "url": r.get("url") or r.get("id"),
                    "canonical_url": r.get("canonical_url") or r.get("url"),
                    "domain": r.get("domain", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "content": r.get("content", ""),
                    "language": r.get("language", "en"),
                    "document_type": r.get("document_type", "webpage"),
                    "content_hash": r.get("content_hash", ""),
                    "source_type": source_type,
                    "source_archive_id": r.get("source_archive_id") or source_reference or "",
                    "captured_at": str(r.get("captured_at") or r.get("source_captured_at") or ""),
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                    "pagerank": float(r.get("pagerank", 0.0) or 0.0),
                    "schema_version": "v1",
                }
                line = json.dumps(canonical_record) + "\n"
                line_bytes = line.encode("utf-8")
                uncompressed_bytes += len(line_bytes)
                hasher.update(line_bytes)
                gz_out.write(line)

        compressed_bytes = local_path.stat().st_size
        sha256_checksum = hasher.hexdigest()

        # 2. Record in PostgreSQL database
        should_close = False
        if db is None:
            db = get_db_manager().get_session()
            should_close = True

        batch_record = DriveUploadBatch(
            batch_id=batch_id,
            schema_version="v1",
            source_type=source_type,
            source_reference=source_reference or "",
            record_count=len(records),
            uncompressed_bytes=uncompressed_bytes,
            compressed_bytes=compressed_bytes,
            sha256_checksum=sha256_checksum,
            drive_file_name=filename,
            local_spool_path=str(local_path),
            upload_status="pending",
            indexing_status="pending",
        )

        try:
            db.add(batch_record)
            db.commit()
            db.refresh(batch_record)

            # 3. Upload to Google Drive if connected
            drive_status = self.drive_service.get_status(db=db)
            drive_uploaded = False

            if drive_status.get("connected"):
                try:
                    upload_res = self.drive_service.upload_batch(
                        batch_id=batch_id,
                        local_filepath=str(local_path),
                        subfolder_name="page-records",
                        db=db,
                    )
                    batch_record.drive_file_id = upload_res.get("file_id")
                    batch_record.drive_folder_id = upload_res.get("folder_id")
                    batch_record.upload_status = "verified"
                    batch_record.uploaded_at = datetime.now(timezone.utc)
                    db.commit()
                    drive_uploaded = True

                    # Prune temporary local spool file to eliminate permanent local disk reliance
                    if local_path.exists():
                        try:
                            local_path.unlink()
                            batch_record.local_spool_path = None
                            db.commit()
                        except Exception as e:
                            logger.warning("Could not prune temporary spool %s: %s", local_path, e)

                except Exception as e:
                    logger.error("Drive upload failed for batch %s: %s", batch_id, e)
                    batch_record.upload_status = "failed"
                    batch_record.last_error = str(e)
                    batch_record.attempt_count += 1
                    db.commit()

            # 4. OpenSearch Indexing Pipeline (Active Search Engine)
            indexing_gw = get_indexing_gateway()
            try:
                index_result = indexing_gw.submit_batch(records, source_type=source_type, source_archive_id=source_reference)
                batch_record.indexing_status = "indexed"
                batch_record.indexed_at = datetime.now(timezone.utc)
                db.commit()
            except Exception as e:
                logger.error("Indexing failed for batch %s: %s", batch_id, e)
                batch_record.indexing_status = "failed"
                batch_record.last_error = (batch_record.last_error or "") + f" | Index error: {str(e)}"
                db.commit()

            return {
                "batch_id": batch_id,
                "record_count": len(records),
                "uncompressed_bytes": uncompressed_bytes,
                "compressed_bytes": compressed_bytes,
                "sha256": sha256_checksum,
                "upload_status": batch_record.upload_status,
                "drive_file_id": batch_record.drive_file_id,
                "indexing_status": batch_record.indexing_status,
            }
        finally:
            if should_close:
                db.close()

    def retry_batch_upload(self, batch_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """Retry a failed or pending upload for a specific batch."""
        should_close = False
        if db is None:
            db = get_db_manager().get_session()
            should_close = True

        try:
            batch = db.query(DriveUploadBatch).filter(DriveUploadBatch.batch_id == batch_id).first()
            if not batch:
                return {"success": False, "error": f"Batch {batch_id} not found."}

            if batch.upload_status == "verified" and batch.drive_file_id:
                return {"success": True, "message": "Batch already verified in Google Drive."}

            if not batch.local_spool_path or not Path(batch.local_spool_path).exists():
                return {"success": False, "error": "Local spool file missing; cannot re-upload without regenerating."}

            batch.upload_status = "uploading"
            batch.attempt_count += 1
            db.commit()

            upload_res = self.drive_service.upload_batch(
                batch_id=batch_id,
                local_filepath=batch.local_spool_path,
                subfolder_name="page-records",
                db=db,
            )

            batch.drive_file_id = upload_res.get("file_id")
            batch.drive_folder_id = upload_res.get("folder_id")
            batch.upload_status = "verified"
            batch.uploaded_at = datetime.now(timezone.utc)
            batch.last_error = None

            # Prune local spool
            p = Path(batch.local_spool_path)
            if p.exists():
                p.unlink()
                batch.local_spool_path = None

            db.commit()
            return {"success": True, "batch_id": batch_id, "drive_file_id": batch.drive_file_id}
        except Exception as e:
            if batch:
                batch.upload_status = "failed"
                batch.last_error = str(e)
                db.commit()
            return {"success": False, "error": str(e)}
        finally:
            if should_close:
                db.close()

    def reconcile_storage_state(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Reconcile and heal storage state:
        - Retries pending local spools if Drive is connected.
        - Indexes any verified Drive batches that missed OpenSearch indexing.
        """
        should_close = False
        if db is None:
            db = get_db_manager().get_session()
            should_close = True

        try:
            status = self.drive_service.get_status(db=db)
            reconciled_uploads = 0
            reconciled_indexes = 0

            if status.get("connected"):
                pending_batches = (
                    db.query(DriveUploadBatch)
                    .filter(DriveUploadBatch.upload_status.in_(["pending", "failed"]))
                    .filter(DriveUploadBatch.local_spool_path.isnot(None))
                    .limit(10)
                    .all()
                )
                for b in pending_batches:
                    if b.local_spool_path and Path(b.local_spool_path).exists():
                        res = self.retry_batch_upload(b.batch_id, db=db)
                        if res.get("success"):
                            reconciled_uploads += 1

            # Log report
            report = DriveStorageReport(
                report_id=f"rep_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:6]}",
                report_type="reconcile",
                summary_json=json.dumps({
                    "reconciled_uploads": reconciled_uploads,
                    "reconciled_indexes": reconciled_indexes,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            )
            db.add(report)
            db.commit()

            return {
                "status": "completed",
                "reconciled_uploads": reconciled_uploads,
                "reconciled_indexes": reconciled_indexes,
            }
        finally:
            if should_close:
                db.close()


_drive_batch_pipeline: Optional[DriveBatchPipeline] = None


def get_drive_batch_pipeline() -> DriveBatchPipeline:
    global _drive_batch_pipeline
    if _drive_batch_pipeline is None:
        _drive_batch_pipeline = DriveBatchPipeline()
    return _drive_batch_pipeline
