import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from app.schemas.search import (
    SearchResponse,
    SuggestionsResponse,
    HealthResponse,
    SearchStatsResponse,
)
from app.services.search_service import SearchService
from app.services.health_service import HealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Search"])
search_service = SearchService()
health_service = HealthService()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Reports the live health and latency of backend, OpenSearch, and PostgreSQL dependencies.",
)
def get_health():
    health = health_service.check_health()
    return health


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search Engine Query",
    description="Execute full-text BM25 search across indexed documents with pagination, domain filtering, and highlighting.",
)
def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query string"),
    page: int = Query(default=1, ge=1, le=1000, description="Page number (1-indexed)"),
    size: int = Query(default=10, ge=1, le=50, description="Number of results per page"),
    lang: Optional[str] = Query(default=None, max_length=10, description="Language filter (e.g. 'en')"),
    domain: Optional[str] = Query(default=None, max_length=255, description="Domain filter"),
    explain: bool = Query(default=False, description="Include ranking explanation signals and feature weights"),
):
    clean_q = q.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query string cannot be empty or purely whitespace.",
        )

    try:
        response = search_service.search(
            query=clean_q,
            page=page,
            size=size,
            language=lang,
            domain=domain,
            explain=explain,
        )
        return response
    except Exception as e:
        logger.exception("Error executing search for query '%s': %s", clean_q, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the search query: {str(e)}",
        )


@router.get(
    "/suggestions",
    response_model=SuggestionsResponse,
    summary="Search Suggestions / Autocomplete",
    description="Returns prefix and phrase suggestions based on indexed document titles.",
)
def suggestions(
    q: str = Query(..., min_length=1, max_length=100, description="Query prefix"),
    limit: int = Query(default=5, ge=1, le=20, description="Max suggestions to return"),
):
    clean_q = q.strip()
    if not clean_q:
        return SuggestionsResponse(query="", suggestions=[])

    try:
        return search_service.suggestions(clean_q, size=limit)
    except Exception as e:
        logger.warning("Error fetching suggestions for prefix '%s': %s", clean_q, e)
        return SuggestionsResponse(query=clean_q, suggestions=[])


@router.get(
    "/search/stats",
    response_model=SearchStatsResponse,
    summary="Index Statistics",
    description="Returns aggregate index size, document counts, and top indexed domains.",
)
def search_stats():
    try:
        return search_service.stats()
    except Exception as e:
        logger.exception("Error fetching search stats: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve search index statistics.",
        )
