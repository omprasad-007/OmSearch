# OM Search — Web Crawler Architecture & Operations Manual (Phase 2)

## 1. Overview

The OM Search Crawler is an independent, respectful, and resilient web crawling system designed to discover, fetch, extract, and incrementally index web pages into the OM Search engine.

It operates strictly asynchronously from search requests and adheres to conservative safety defaults for running locally or in production.

---

## 2. Crawler Core Modules

### 2.1 URL Frontier (`crawler/om_crawler/frontier.py`)
Backed by PostgreSQL (with local SQLite fallback for dev/testing), managing an explicit state machine:
- `DISCOVERED`: Link found on a parent page.
- `QUEUED`: Normalized, passed validation, ready to crawl.
- `FETCHING`: Leased by a worker process (lease duration default: 90s).
- `FETCHED`: Successfully retrieved and extracted.
- `SKIPPED_POLICY`: Excluded by depth, allowlist/denylist, or forbidden extensions.
- `RETRY_WAIT`: Scheduled for exponential backoff retry after transient error.
- `FAILED`: Permanently failed after exceeding max attempts (default: 3).
- `BLOCKED`: Blocked by `robots.txt` directives or operator rules.
- `DUPLICATE`: Cryptographic content hash matches an existing document.

#### Atomic Worker Leasing & Crash Recovery
- Workers claim batches with `FOR UPDATE SKIP LOCKED` (PostgreSQL) and set a `lease_expires_at` timestamp.
- If a worker crashes or is killed, `reset_expired_leases()` automatically reclaims orphaned records and returns them to `QUEUED` status so jobs resume without recrawling finished pages.

---

## 3. Network Security & SSRF Defense (`crawler/om_crawler/network_safety.py`)

Untrusted web content is parsed defensively:
- **Strict Protocol Enforcement**: Only `http://` and `https://` schemes accepted.
- **Embedded Credentials Blocked**: URLs containing `user:pass@host` are immediately rejected.
- **Anti-SSRF IP Validation**:
  - All hostnames are DNS-resolved prior to connection.
  - Every resolved IP is verified against RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), and multicast.
  - Explicit cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`) are blocked.
- **Response Size Bounding**: Hard response limit of 2 MB (`MAX_RESPONSE_BYTES`) to prevent decompression bombs and memory exhaustion.
- **Content-Type Filter**: Only `text/html` and `application/xhtml+xml` documents are accepted. Executables, archives, and binaries are rejected.
- **Redirect Target Validation**: Every hop in a redirect chain is re-validated for safety and allowlist compliance.

---

## 4. Robots.txt Compliance & Politeness (`crawler/om_crawler/robots_policy.py`)

- **User-Agent**:
  `OMSearchBot/0.2 (+https://omsearch.org/bot; bot@omsearch.org)`
  (Configurable via environment variables or operator options).
- **Caching**: `robots.txt` is cached for 24 hours (`cache_ttl = 86400`).
- **Conservative Error Handling**:
  - `404 Not Found`: Treated as no restrictions.
  - `5xx Server Error` / Connection failure: Treated conservatively (crawling blocked until server recovers).
- **Per-Host Rate Limiting**:
  - Defaults to a minimum of 1.5–2.0 seconds between requests to the same domain.
  - Honors site-specific `Crawl-delay` directives if higher than default.
- **Operator Overrides**:
  - `set_global_pause(True)`: Halts all active crawler fetch loops immediately.
  - `disable_domain("spamsite.com")`: Blacklists specific domains in real time.

---

## 5. HTML Content Extraction (`crawler/om_crawler/extractor.py`)

1. **Title & Metadata**: Parses page `<title>`, `<meta name="description">`, language (`<html lang="...">`), and publication dates.
2. **Main Article Extraction**: Uses `trafilatura` for clean readable body extraction, discarding navigation bars, footers, scripts, and styles.
3. **BeautifulSoup Fallback**: Gracefully falls back to structured tag decomposition if Trafilatura returns insufficient text.
4. **Canonical Validation**: Validates `<link rel="canonical">` before associating it with the document. Does not blindly trust cross-domain canonical links.
5. **Content Fingerprinting**: Calculates a SHA-256 hash of whitespace-collapsed text body for duplicate detection.

---

## 6. Incremental Indexing (`crawler/om_crawler/indexing_pipeline.py`)

- **Hash Deduplication**: Compares newly computed SHA-256 content hash with existing database records.
- **Skip Unchanged Writes**: If the page content has not changed since the last fetch, OpenSearch indexing is skipped to conserve I/O and cluster resources.
- **Idempotent Updates**: New or changed pages update OpenSearch deterministically using `compute_url_id(canonical_url)`.
- **Lifecycle Tracking**: Every action (`discovered`, `fetched_unchanged`, `indexed`, `deduplicated`) is recorded in PostgreSQL.

---

## 7. Operator API & CLI Commands

### API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/crawl/jobs` | Create and launch a crawl job from seed URLs |
| `GET` | `/api/v1/crawl/jobs/{id}` | Inspect live job status, pages crawled and indexed |
| `GET` | `/api/v1/crawl/stats` | View aggregate frontier status counts |
| `GET` | `/api/v1/crawl/failures` | List recent crawl errors and reasons |
| `POST` | `/api/v1/crawl/jobs/{id}/pause` | Pause active job |
| `POST` | `/api/v1/crawl/jobs/{id}/resume` | Resume paused job |
| `POST` | `/api/v1/crawl/jobs/{id}/cancel` | Permanently terminate job |

### CLI Management Tool
```bash
# Start a crawl job:
python scripts/run_crawler.py start --seeds "https://docs.python.org/3/" --max-pages 25 --max-depth 2

# View frontier counts:
python scripts/run_crawler.py stats

# Inspect recent errors:
python scripts/run_crawler.py failures --limit 10

# Reset orphaned leases:
python scripts/run_crawler.py reset-leases
```
