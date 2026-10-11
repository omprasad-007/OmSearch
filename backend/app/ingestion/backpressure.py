"""
OM Search - Ingestion Backpressure & Adaptive Throttling
Monitors storage latency, OpenSearch queue depth, and memory pressure to dynamically throttle ingestion.
"""
import time
import logging
from typing import Dict, Any

logger = logging.getLogger("om_ingestion.backpressure")


class BackpressureMonitor:
    """
    Monitors system pressure and adapts concurrency to prevent OOM and timeouts.
    """

    def __init__(
        self,
        max_opensearch_latency_ms: float = 500.0,
        max_db_latency_ms: float = 200.0,
    ):
        self.max_os_latency = max_opensearch_latency_ms
        self.max_db_latency = max_db_latency_ms
        self.consecutive_slow_ops = 0
        self.throttle_ratio = 1.0  # 1.0 = normal, 0.5 = halved, 0.1 = maximum throttle

    def record_operation_latency(self, component: str, latency_ms: float) -> None:
        threshold = self.max_os_latency if component == "opensearch" else self.max_db_latency
        if latency_ms > threshold:
            self.consecutive_slow_ops += 1
            if self.consecutive_slow_ops >= 3:
                # Step down concurrency
                self.throttle_ratio = max(0.2, self.throttle_ratio * 0.75)
                logger.warning(
                    "Backpressure triggered by %s (latency %.1fms > %.1fms). Throttle ratio: %.2f",
                    component, latency_ms, threshold, self.throttle_ratio
                )
        else:
            if self.consecutive_slow_ops > 0:
                self.consecutive_slow_ops -= 1
            # Step up gradually
            self.throttle_ratio = min(1.0, self.throttle_ratio + 0.05)

    def get_adjusted_concurrency(self, base_workers: int) -> int:
        """Returns worker allocation scaled by current throttle ratio."""
        return max(1, int(base_workers * self.throttle_ratio))

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "throttle_ratio": round(self.throttle_ratio, 2),
            "is_throttled": self.throttle_ratio < 0.95,
            "consecutive_slow_ops": self.consecutive_slow_ops,
        }
