from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class DocumentModel(BaseModel):
    """Normalized document model mapped to OpenSearch schema."""
    id: str = Field(description="Unique document ID (hash of canonical URL)")
    url: str = Field(description="Original fetched URL")
    canonical_url: str = Field(description="Normalized canonical URL")
    domain: str = Field(description="Domain host of the document")
    title: str = Field(default="", description="Extracted document title")
    content: str = Field(default="", description="Full extracted text body")
    snippet: str = Field(default="", description="Summarized snippet or excerpt")
    language: str = Field(default="en", description="Detected language code")
    published_at: Optional[datetime] = Field(default=None, description="Publication timestamp if available")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Crawl/fetch timestamp")
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Indexing timestamp")
    content_hash: str = Field(description="SHA-256 hash of cleaned text content")
    http_status: int = Field(default=200, description="HTTP response status code")
    document_type: str = Field(default="webpage", description="MIME or document category (webpage, article, pdf)")

    def to_opensearch_dict(self) -> dict:
        data = self.model_dump()
        # Format datetimes to ISO 8601 strings
        for dt_field in ["published_at", "fetched_at", "indexed_at"]:
            if data.get(dt_field) is not None and isinstance(data[dt_field], datetime):
                data[dt_field] = data[dt_field].isoformat()
        return data
