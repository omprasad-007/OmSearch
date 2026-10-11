from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class SearchQueryRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=200, description="Search query string")
    page: int = Field(default=1, ge=1, le=1000, description="Page number (1-indexed)")
    size: int = Field(default=10, ge=1, le=50, description="Number of results per page")

    @field_validator("q")
    @classmethod
    def clean_query(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Query string cannot be empty or only whitespace")
        return trimmed


class SearchResultItem(BaseModel):
    id: str
    url: str
    canonical_url: str
    domain: str
    title: str
    snippet: str
    language: str = "en"
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None
    score: float = 0.0
    document_type: str = "webpage"
    highlights: List[str] = Field(default_factory=list)
    explanation: Optional[List[str]] = Field(default_factory=list)
    features: Optional[Dict[str, float]] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    size: int
    total_pages: int
    took_ms: float
    results: List[SearchResultItem]
    is_early_index: bool = True
    message: Optional[str] = None
    query_intent: Optional[str] = None
    spelling_suggestion: Optional[str] = None
    ranking_version: Optional[str] = None


class SuggestionsResponse(BaseModel):
    query: str
    suggestions: List[str]


class ServiceHealth(BaseModel):
    status: str  # healthy, degraded, unreachable
    latency_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str  # healthy, degraded, unhealthy
    app_version: str
    timestamp: datetime
    services: Dict[str, ServiceHealth]


class SearchStatsResponse(BaseModel):
    total_documents: int
    index_name: str
    index_alias: str
    status: str
    domains_count: int
    top_domains: List[Dict[str, Any]]
    storage_bytes: Optional[int] = None
    live_crawled_count: Optional[int] = 0
    cloud_archived_count: Optional[int] = 0
    cloud_storage_formatted: Optional[str] = "0 MB"
