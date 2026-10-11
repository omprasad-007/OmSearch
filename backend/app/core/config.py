from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "OM Search"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server Limits
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    MAX_REQUEST_SIZE_BYTES: int = 1_048_576  # 1MB
    REQUEST_TIMEOUT_SECONDS: float = 5.0

    # Search Limits
    MAX_QUERY_LENGTH: int = 200
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 50

    # OpenSearch
    OPENSEARCH_HOST: str = "127.0.0.1"
    OPENSEARCH_PORT: int = 9200
    OPENSEARCH_USE_SSL: bool = False
    OPENSEARCH_VERIFY_CERTS: bool = False
    OPENSEARCH_USERNAME: str = "admin"
    OPENSEARCH_PASSWORD: str = "admin"
    OPENSEARCH_INDEX_NAME: str = "om_documents_v1"
    OPENSEARCH_INDEX_ALIAS: str = "om_documents"
    OPENSEARCH_TIMEOUT_SECONDS: float = 3.0

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://om_user:om_password@127.0.0.1:5432/om_search"
    # Fallback to local SQLite when Postgres is not running locally during development/tests
    SQLITE_FALLBACK_URL: str = "sqlite:///./om_search_local.db"
    USE_SQLITE_FALLBACK_IF_UNAVAILABLE: bool = True

    # Unified Ingestion Platform
    INGESTION_SCHEDULING_PROFILE: str = "STEADY_STATE"
    LIVE_CRAWLER_ENABLED: bool = True
    ARCHIVE_IMPORTER_ENABLED: bool = True
    AUTO_START_ARCHIVE_ON_LAUNCH: bool = False
    MAX_BULK_INDEX_BATCH_SIZE: int = 100
    OPERATOR_API_KEY: str = "om-operator-secret-key-2026"

    # Google Drive Storage & Cloud Architecture (Google One 5 TB)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/api/v1/storage/google-drive/callback"
    GOOGLE_DRIVE_ROOT_FOLDER_NAME: str = "OM-Search-Data"
    GOOGLE_DRIVE_ROOT_FOLDER_ID: str = ""
    GOOGLE_DRIVE_SCOPES: List[str] = ["https://www.googleapis.com/auth/drive.file"]
    GOOGLE_DRIVE_BATCH_MAX_RECORDS: int = 5000
    GOOGLE_DRIVE_BATCH_MAX_BYTES: int = 25 * 1024 * 1024  # 25 MB compressed batch
    GOOGLE_DRIVE_UPLOAD_CONCURRENCY: int = 2
    GOOGLE_DRIVE_RETRY_LIMIT: int = 3
    GOOGLE_DRIVE_STORAGE_BUDGET_BYTES: int = 5 * 1024 * 1024 * 1024 * 1024  # 5 TB
    GOOGLE_DRIVE_TEMP_DIR: str = "data/drive_spool"
    GOOGLE_DRIVE_ENABLED: bool = False
    GOOGLE_ENCRYPTION_KEY: str = ""

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://omsearch.web.app",
        "https://omsearch.firebaseapp.com",
        "https://one-for-all-5e842.web.app",
        "https://one-for-all-5e842.firebaseapp.com",
    ]

    @property
    def opensearch_url(self) -> str:
        protocol = "https" if self.OPENSEARCH_USE_SSL else "http"
        return f"{protocol}://{self.OPENSEARCH_HOST}:{self.OPENSEARCH_PORT}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
