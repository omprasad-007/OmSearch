import sys
from pathlib import Path
import logging
from contextlib import asynccontextmanager

# Ensure project root is in sys.path for crawler module
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.v1.router import router as api_v1_router
from app.api.v1.crawl_router import router as crawl_router
from app.api.v1.ingestion_router import router as ingestion_router
from app.api.v1.storage_router import router as storage_router
from app.repositories.opensearch_repo import get_opensearch_repo
from app.repositories.database import get_db_manager

settings = get_settings()
setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger("om_search")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    # Ensure database tables
    try:
        get_db_manager()
        logger.info("Database schema verified.")
    except Exception as e:
        logger.warning("Database initialization warning: %s", e)

    # Check/create OpenSearch index if connected
    try:
        os_repo = get_opensearch_repo()
        if os_repo.ping():
            os_repo.ensure_index()
            logger.info("OpenSearch index verified.")
        else:
            logger.info("OpenSearch is not currently reachable; starting in resilient mode.")
            os_repo._ensure_fallback_store()
            os_repo._rebuild_inverted_index()
            logger.info("In-memory inverted index pre-warmed (%d documents).", len(os_repo._fallback_store))
    except Exception as e:
        logger.warning("OpenSearch initialization warning: %s", e)

    # Pre-warm SearchService pipeline for instant sub-5ms first search
    try:
        from app.services.search_service import SearchService
        _search_svc = SearchService()
        _search_svc.search("quantum", page=1, size=1)
        logger.info("Search pipeline pre-warmed and ready.")
    except Exception as e:
        logger.debug("Search pipeline warmup notice: %s", e)

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title="OM Search Engine API",
    description="High-performance, independent web search engine backend foundation.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_size_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_REQUEST_SIZE_BYTES:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "Request payload exceeds allowed limit (1MB)."},
        )
    return await call_next(request)


# Include API v1 routes
app.include_router(api_v1_router)
app.include_router(crawl_router)
app.include_router(ingestion_router)
app.include_router(storage_router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/", tags=["System"])
async def root():
    return {
        "engine": "OM Search",
        "version": settings.APP_VERSION,
        "status": "online",
        "documentation": "/docs",
        "health": "/api/v1/health",
        "search": "/api/v1/search?q={query}",
    }
