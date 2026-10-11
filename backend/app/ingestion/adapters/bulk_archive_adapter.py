"""
OM Search - Bulk Archive Importer Adapter
Manages archive manifests, partition chunks, checkpoints, and historical record extraction.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.repositories.database import SourceType
from app.ingestion.adapters.base import BaseSourceAdapter, WorkUnit, ExtractedRecord

logger = logging.getLogger("om_ingestion.adapters.archive")


class BulkArchiveImporterAdapter(BaseSourceAdapter):
    """
    Adapter managing partitioned bulk archive ingestion and checkpoints.
    """

    def __init__(
        self,
        archive_dir: Optional[str] = None,
        checkpoint_file: Optional[str] = None,
        concurrency_limit: int = 6,
    ):
        self.archive_dir = Path(archive_dir) if archive_dir else Path("data/archives")
        self.checkpoint_file = Path(checkpoint_file) if checkpoint_file else Path("data/archive_checkpoint.json")
        self._concurrency_limit = concurrency_limit
        self._checkpoints: Dict[str, Dict[str, Any]] = self._load_checkpoints()

    @property
    def source_type(self) -> str:
        return SourceType.ARCHIVE_IMPORTER

    @property
    def default_concurrency_limit(self) -> int:
        return self._concurrency_limit

    @property
    def rate_limit_delay(self) -> float:
        return 0.0  # Bulk files are read locally/internally without remote host rate limits

    def _load_checkpoints(self) -> Dict[str, Dict[str, Any]]:
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not load archive checkpoint file: %s", e)
        return {}

    def _save_checkpoints(self) -> None:
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(self._checkpoints, f, indent=2)
        except Exception as e:
            logger.error("Could not save archive checkpoint: %s", e)

    def register_partition(self, partition_id: str, partition_path: str, record_count: int = 0) -> WorkUnit:
        """Explicitly registers an archive partition file as a work unit."""
        return WorkUnit(
            unit_id=partition_id,
            source_type=self.source_type,
            work_type="archive_partition",
            payload={"path": str(partition_path), "record_count": record_count},
            priority=10,
            estimated_cost=float(max(1, record_count)),
            created_at=datetime.now(timezone.utc),
        )

    def discover_work_units(self, batch_size: int = 50) -> List[WorkUnit]:
        """
        Scans archive_dir for uncompleted partition files (.json, .jsonl).
        """
        units: List[WorkUnit] = []
        if not self.archive_dir.exists():
            return units

        for p_file in sorted(self.archive_dir.glob("*.json*")):
            part_id = p_file.stem
            # Skip if already marked COMPLETED in checkpoint
            if self._checkpoints.get(part_id, {}).get("status") == "COMPLETED":
                continue

            units.append(
                WorkUnit(
                    unit_id=part_id,
                    source_type=self.source_type,
                    work_type="archive_partition",
                    payload={"path": str(p_file)},
                    priority=5,
                    created_at=datetime.now(timezone.utc),
                )
            )
            if len(units) >= batch_size:
                break

        return units

    def execute_work_unit(self, unit: WorkUnit) -> List[ExtractedRecord]:
        """
        Parses the archive partition file and converts items to ExtractedRecord instances.
        """
        path_str = unit.payload.get("path")
        if not path_str or not os.path.exists(path_str):
            raise FileNotFoundError(f"Archive partition file not found: {path_str}")

        records: List[ExtractedRecord] = []
        part_id = unit.unit_id

        # Read JSON array or JSON Lines
        with open(path_str, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("["):
                raw_items = json.loads(content)
            else:
                raw_items = [json.loads(line) for line in content.splitlines() if line.strip()]

        for item in raw_items:
            url = item.get("url")
            if not url:
                continue

            captured_at = None
            if item.get("captured_at") or item.get("source_captured_at"):
                date_str = item.get("captured_at") or item.get("source_captured_at")
                try:
                    captured_at = datetime.fromisoformat(date_str)
                except Exception:
                    pass

            records.append(
                ExtractedRecord(
                    url=url,
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    snippet=item.get("snippet", ""),
                    canonical_url=item.get("canonical_url"),
                    source_captured_at=captured_at,
                    live_fetched_at=None,
                    language=item.get("language", "en"),
                    http_status=item.get("http_status", 200),
                    headers_json=json.dumps(item.get("headers", {})) if item.get("headers") else None,
                    source_archive_id=part_id,
                    outgoing_links=item.get("links", []),
                )
            )

        return records

    def complete_work_unit(self, unit: WorkUnit, status: str, error: Optional[str] = None) -> None:
        """
        Records partition completion status in durable checkpoint.
        """
        part_id = unit.unit_id
        self._checkpoints[part_id] = {
            "status": status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "path": unit.payload.get("path"),
            "error": error,
        }
        self._save_checkpoints()

    def classify_error(self, exception: Exception) -> str:
        if isinstance(exception, (json.JSONDecodeError, ValueError)):
            return "PERMANENT"
        if isinstance(exception, (FileNotFoundError, PermissionError)):
            return "PERMANENT"
        return "TRANSIENT"

    def get_checkpoint(self) -> Dict[str, Any]:
        completed = sum(1 for c in self._checkpoints.values() if c.get("status") == "COMPLETED")
        failed = sum(1 for c in self._checkpoints.values() if c.get("status") == "FAILED")
        return {
            "total_partitions": len(self._checkpoints),
            "completed_partitions": completed,
            "failed_partitions": failed,
        }
