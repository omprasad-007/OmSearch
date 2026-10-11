"""
OM Search - Unified Ingestion Coordinator
Coordinates live crawling and bulk archive imports through durable scheduling,
source adapters, shared indexing gateway, and operational policy controls.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from app.repositories.database import SourceType, TaskPriorityClass
from app.ingestion.adapters.base import BaseSourceAdapter, WorkUnit, ExtractedRecord
from app.ingestion.adapters.live_crawler_adapter import LiveCrawlerAdapter
from app.ingestion.adapters.bulk_archive_adapter import BulkArchiveImporterAdapter
from app.ingestion.policy import IngestionPolicyEngine, SchedulingProfile
from app.ingestion.scheduler import DurableTaskScheduler
from app.ingestion.indexing_gateway import SharedIndexingGateway

logger = logging.getLogger("om_ingestion.coordinator")


class IngestionCoordinator:
    """
    Central control plane and worker orchestration for all ingestion sources.
    Does not load large datasets into memory; delegates work to adapters and gateway.
    """

    def __init__(
        self,
        policy_engine: Optional[IngestionPolicyEngine] = None,
        scheduler: Optional[DurableTaskScheduler] = None,
        gateway: Optional[SharedIndexingGateway] = None,
    ):
        self.policy_engine = policy_engine or IngestionPolicyEngine()
        self.scheduler = scheduler or DurableTaskScheduler(policy_engine=self.policy_engine)
        self.gateway = gateway or SharedIndexingGateway()

        # Initialize source adapters
        self.adapters: Dict[str, BaseSourceAdapter] = {
            SourceType.LIVE_CRAWLER: LiveCrawlerAdapter(),
            SourceType.ARCHIVE_IMPORTER: BulkArchiveImporterAdapter(),
        }

    @property
    def live_crawler_adapter(self) -> BaseSourceAdapter:
        return self.adapters[SourceType.LIVE_CRAWLER]

    @property
    def archive_adapter(self) -> BaseSourceAdapter:
        return self.adapters[SourceType.ARCHIVE_IMPORTER]

    @property
    def identity_service(self):
        return self.gateway.identity_service

    @property
    def monitor(self):
        from app.ingestion.monitoring import UnifiedIngestionMonitor
        return UnifiedIngestionMonitor(coordinator=self)

    def submit_work(
        self,
        source_type: str,
        work_unit_id: str,
        priority_class: str = TaskPriorityClass.ROUTINE,
        payload: Optional[Dict[str, Any]] = None,
    ):
        return self.scheduler.submit_task(
            source_type=source_type,
            work_unit_id=work_unit_id,
            priority_class=priority_class,
            payload=payload,
        )

    def register_adapter(self, adapter: BaseSourceAdapter) -> None:
        self.adapters[adapter.source_type] = adapter

    def discover_and_enqueue(self, batch_size: int = 50) -> Dict[str, int]:
        """
        Discovers work units from all enabled, unpaused adapters and schedules them.
        """
        if self.policy_engine.globally_paused:
            logger.info("Discovery skipped: ingestion is globally paused.")
            return {}

        results = {}
        for source_type, adapter in self.adapters.items():
            if not self.policy_engine.is_source_runnable(source_type):
                results[source_type] = 0
                continue

            try:
                units = adapter.discover_work_units(batch_size=batch_size)
                enqueued = 0
                for u in units:
                    p_class = (
                        TaskPriorityClass.BULK_ARCHIVE
                        if source_type == SourceType.ARCHIVE_IMPORTER
                        else TaskPriorityClass.ROUTINE
                    )
                    self.scheduler.submit_task(
                        source_type=source_type,
                        work_unit_id=u.unit_id,
                        priority_class=p_class,
                        base_priority=u.priority,
                        estimated_cost=u.estimated_cost,
                        payload=u.payload,
                    )
                    enqueued += 1
                results[source_type] = enqueued
            except Exception as e:
                logger.error("Error discovering work units for %s: %s", source_type, e)
                results[source_type] = 0

        return results

    def process_one_task(self, worker_id: str = "coord-worker-1") -> Optional[Dict[str, Any]]:
        """
        Claims a single highest-priority task, executes it via its adapter,
        and indexes the extracted records through the shared gateway.
        """
        if self.policy_engine.globally_paused:
            return None

        # Reclaim expired leases first
        self.scheduler.reclaim_expired_leases()
        self.scheduler.apply_aging()

        # Claim next task
        task = self.scheduler.claim_next_task(worker_id=worker_id)
        if not task:
            return None

        adapter = self.adapters.get(task.source_type)
        if not adapter:
            self.scheduler.fail_task(task.task_id, f"No registered adapter for {task.source_type}", is_transient=False)
            return None

        unit = WorkUnit(
            unit_id=task.work_unit_id,
            source_type=task.source_type,
            work_type="task_execution",
            payload=json.loads(task.payload_json or "{}"),
            priority=int(task.priority_score),
            created_at=task.created_at,
        )

        try:
            # 1. Execute source-specific extraction
            records: List[ExtractedRecord] = adapter.execute_work_unit(unit)

            # 2. Ingest through shared gateway
            indexed_count = 0
            for rec in records:
                res = self.gateway.submit_document(
                    raw_url=rec.url,
                    title=rec.title,
                    content=rec.content,
                    snippet=rec.snippet,
                    canonical_hint=rec.canonical_url,
                    source_type=task.source_type,
                    source_archive_id=rec.source_archive_id or task.work_unit_id,
                    source_captured_at=rec.source_captured_at,
                    live_fetched_at=rec.live_fetched_at,
                    language=rec.language,
                    http_status=rec.http_status,
                    headers_json=rec.headers_json,
                )
                if res.get("indexed"):
                    indexed_count += 1

            # 3. Acknowledge work unit in adapter and scheduler
            adapter.complete_work_unit(unit, status="COMPLETED")
            self.scheduler.complete_task(task.task_id)

            return {
                "task_id": task.task_id,
                "source_type": task.source_type,
                "work_unit_id": task.work_unit_id,
                "status": "COMPLETED",
                "records_extracted": len(records),
                "indexed_count": indexed_count,
            }

        except Exception as e:
            err_str = str(e)
            error_class = adapter.classify_error(e)
            is_transient = error_class == "TRANSIENT"

            adapter.complete_work_unit(unit, status="FAILED", error=err_str)
            self.scheduler.fail_task(task.task_id, error=err_str, is_transient=is_transient)

            logger.warning("Task %s failed (%s): %s", task.task_id, error_class, err_str)
            return {
                "task_id": task.task_id,
                "source_type": task.source_type,
                "status": "FAILED",
                "error_class": error_class,
                "error": err_str,
            }

    def run_coordinator_cycle(self, max_tasks: int = 10) -> Dict[str, Any]:
        """
        Executes an end-to-end iteration of discovery and work processing.
        """
        enqueued = self.discover_and_enqueue()
        processed = 0
        succeeded = 0
        failed = 0

        for _ in range(max_tasks):
            res = self.process_one_task()
            if not res:
                break
            processed += 1
            if res.get("status") == "COMPLETED":
                succeeded += 1
            else:
                failed += 1

        return {
            "enqueued": enqueued,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Returns full monitoring status across policy, scheduler, and adapters.
        """
        adapter_checkpoints = {st: a.get_checkpoint() for st, a in self.adapters.items()}
        queue_stats = self.scheduler.get_queue_stats()
        policy_stats = self.policy_engine.to_dict()

        return {
            "status": "PAUSED" if self.policy_engine.globally_paused else "RUNNING",
            "policy": policy_stats,
            "queues": queue_stats,
            "adapters": adapter_checkpoints,
        }
