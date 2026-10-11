"""
OM Search - Unified Ingestion Monitoring & Observability
Gathers end-to-end metrics across sources, scheduler queues, document registry,
historical captures, and backpressure state.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.repositories.database import (
    get_db_manager,
    URLRecord,
    DocumentRegistry,
    HistoricalCapture,
    DocumentAlias,
    IngestionTask,
    FrontierStatus,
)
from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.backpressure import BackpressureMonitor


class UnifiedIngestionMonitor:
    def __init__(
        self,
        coordinator: Optional[IngestionCoordinator] = None,
        backpressure: Optional[BackpressureMonitor] = None,
    ):
        self.coordinator = coordinator or IngestionCoordinator()
        self.backpressure = backpressure or BackpressureMonitor()
        self.db_mgr = get_db_manager()

    def get_full_telemetry(self) -> Dict[str, Any]:
        """
        Compiles exhaustive real-time operational telemetry.
        """
        db = self.db_mgr.get_session()
        try:
            # 1. Database Document Registry & Captures
            unique_docs = db.query(DocumentRegistry).count()
            total_captures = db.query(HistoricalCapture).count()
            aliases_count = db.query(DocumentAlias).count()
            unreconciled_docs = db.query(DocumentRegistry).filter(DocumentRegistry.reconciliation_status != "synced").count()

            # 2. Frontier stats
            total_urls = db.query(URLRecord).count()
            fetched_urls = db.query(URLRecord).filter(URLRecord.status == FrontierStatus.FETCHED).count()
            queued_urls = db.query(URLRecord).filter(URLRecord.status.in_([FrontierStatus.QUEUED, FrontierStatus.RETRY_WAIT])).count()
            failed_urls = db.query(URLRecord).filter(URLRecord.status == FrontierStatus.FAILED).count()

            # 3. Tasks & queues
            queue_stats = self.coordinator.scheduler.get_queue_stats()

            # 4. Backpressure
            bp_stats = self.backpressure.get_metrics()

            # 5. Coordinator and policy
            coord_status = self.coordinator.get_status()

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": coord_status["status"],
                "documents": {
                    "unique_searchable_documents": unique_docs,
                    "total_historical_captures": total_captures,
                    "document_aliases": aliases_count,
                    "unreconciled_documents": unreconciled_docs,
                },
                "frontier": {
                    "total_urls_known": total_urls,
                    "fetched_urls": fetched_urls,
                    "queued_urls": queued_urls,
                    "failed_urls": failed_urls,
                },
                "queues": queue_stats,
                "backpressure": bp_stats,
                "policy": coord_status["policy"],
                "adapters": coord_status["adapters"],
            }
        finally:
            db.close()

    def get_telemetry_metrics(self) -> Dict[str, Any]:
        """
        Calculates rate metrics, queue depths, and indexing throughput.
        """
        full = self.get_full_telemetry()
        queues = full.get("queues", {})
        frontier = full.get("frontier", {})
        docs = full.get("documents", {})
        bp = full.get("backpressure", {})
        return {
            "timestamp": full["timestamp"],
            "status": full["status"],
            "queue_depth_total": queues.get("total_pending", 0),
            "priority_classes": queues.get("by_priority", {}),
            "source_queues": queues.get("by_source", {}),
            "urls_fetched_total": frontier.get("fetched_urls", 0),
            "unique_documents_indexed": docs.get("unique_searchable_documents", 0),
            "historical_captures_preserved": docs.get("total_historical_captures", 0),
            "backpressure_state": bp.get("status", "NORMAL"),
            "backpressure_level": bp.get("level", 0.0),
            "active_leases": queues.get("active_leases", 0),
            "dead_letter_count": queues.get("dead_letter", 0),
        }

