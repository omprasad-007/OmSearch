-- OM Search PostgreSQL Initialization Schema (Phase 2 Frontier)

CREATE TABLE IF NOT EXISTS urls (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    normalized_url TEXT,
    canonical_url TEXT,
    domain VARCHAR(255) NOT NULL,
    scheme VARCHAR(10) DEFAULT 'https',
    discovery_source TEXT,
    depth INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'DISCOVERED',
    priority INTEGER DEFAULT 0,
    attempt_count INTEGER DEFAULT 0,
    next_fetch_at TIMESTAMPTZ,
    last_fetched_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    http_status INTEGER,
    content_hash VARCHAR(64),
    last_error TEXT,
    worker_id VARCHAR(64),
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_urls_normalized ON urls (normalized_url);
CREATE INDEX IF NOT EXISTS idx_urls_canonical ON urls (canonical_url);
CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls (domain);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls (status);
CREATE INDEX IF NOT EXISTS idx_urls_depth ON urls (depth);
CREATE INDEX IF NOT EXISTS idx_urls_priority ON urls (priority);
CREATE INDEX IF NOT EXISTS idx_urls_next_fetch ON urls (next_fetch_at);
CREATE INDEX IF NOT EXISTS idx_urls_lease ON urls (lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_urls_content_hash ON urls (content_hash);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id SERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    config TEXT,
    total_urls INTEGER DEFAULT 0,
    processed_urls INTEGER DEFAULT 0,
    indexed_urls INTEGER DEFAULT 0,
    failed_urls INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs (status);

CREATE TABLE IF NOT EXISTS document_lifecycle (
    id SERIAL PRIMARY KEY,
    url_id INTEGER REFERENCES urls(id) ON DELETE CASCADE,
    canonical_url TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_url_id ON document_lifecycle (url_id);
