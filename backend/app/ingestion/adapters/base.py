"""
OM Search - Source Adapter Interface
Defines the unified ingestion adapter contract for live crawler and bulk archive sources.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WorkUnit:
    unit_id: str
    source_type: str
    work_type: str  # "url_fetch", "archive_partition", "seed_discovery"
    payload: Dict[str, Any]
    priority: int = 0
    estimated_cost: float = 1.0
    created_at: Optional[datetime] = None


@dataclass
class ExtractedRecord:
    url: str
    title: str
    content: str
    snippet: str = ""
    canonical_url: Optional[str] = None
    source_captured_at: Optional[datetime] = None
    live_fetched_at: Optional[datetime] = None
    language: str = "en"
    http_status: int = 200
    headers_json: Optional[str] = None
    source_archive_id: Optional[str] = None
    outgoing_links: List[str] = field(default_factory=list)


class BaseSourceAdapter(ABC):
    """
    Stable adapter interface for ingestion sources.
    Maintains source-specific behavior while exposing a uniform contract to the coordinator.
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Returns the unique source identifier (e.g., 'live_crawler', 'archive_importer')."""
        pass

    @property
    @abstractmethod
    def default_concurrency_limit(self) -> int:
        """Maximum concurrent workers allocated to this source."""
        pass

    @property
    @abstractmethod
    def rate_limit_delay(self) -> float:
        """Politeness or rate-limiting interval between operations in seconds."""
        pass

    @abstractmethod
    def discover_work_units(self, batch_size: int = 50) -> List[WorkUnit]:
        """Discovers pending work units from the source frontier or archive manifests."""
        pass

    @abstractmethod
    def execute_work_unit(self, unit: WorkUnit) -> List[ExtractedRecord]:
        """Executes a claimed work unit and returns extracted, normalized records."""
        pass

    @abstractmethod
    def complete_work_unit(self, unit: WorkUnit, status: str, error: Optional[str] = None) -> None:
        """Acknowledges work unit completion or records failure in the source-specific system."""
        pass

    @abstractmethod
    def classify_error(self, exception: Exception) -> str:
        """Classifies an error as 'TRANSIENT' (retryable) or 'PERMANENT' (terminal)."""
        pass

    @abstractmethod
    def get_checkpoint(self) -> Dict[str, Any]:
        """Returns current checkpoint metadata for resume and recovery."""
        pass
