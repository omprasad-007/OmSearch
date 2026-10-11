from datetime import datetime, timezone
from app.core.config import get_settings
from app.repositories.opensearch_repo import get_opensearch_repo
from app.repositories.database import get_db_manager
from app.schemas.search import HealthResponse, ServiceHealth


class HealthService:
    def __init__(self):
        self.settings = get_settings()
        self.os_repo = get_opensearch_repo()
        self.db_manager = get_db_manager()

    def check_health(self) -> HealthResponse:
        os_health_data = self.os_repo.get_cluster_health()
        db_health_data = self.db_manager.check_health()

        services = {
            "opensearch": ServiceHealth(
                status=os_health_data.get("status", "unknown"),
                latency_ms=os_health_data.get("latency_ms"),
                details=os_health_data.get("details"),
            ),
            "database": ServiceHealth(
                status=db_health_data.get("status", "unknown"),
                latency_ms=db_health_data.get("latency_ms"),
                details=db_health_data.get("details"),
            ),
        }

        # Overall health logic
        statuses = [s.status for s in services.values()]
        if all(st == "healthy" for st in statuses):
            overall_status = "healthy"
        elif any(st in ("healthy", "degraded") for st in statuses):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return HealthResponse(
            status=overall_status,
            app_version=self.settings.APP_VERSION,
            timestamp=datetime.now(timezone.utc),
            services=services,
        )
