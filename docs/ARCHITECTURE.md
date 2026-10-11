# OM Search Engine — System Architecture (Phase 1 & Phase 2)

## 1. Overview and Mission

OM Search is an independent, general-purpose open web search engine foundation. It operates its own pipeline from start to finish:
- **Controlled Web Crawler & Scheduler** (`crawler/om_crawler/`)
- **Persistent URL Frontier** (PostgreSQL / SQLite fallback)
- **Robots.txt & Per-Host Politeness Engine** (Protego compliance & rate limiter)
- **Network Safety & SSRF Shield** (DNS-level private IP and metadata blocking)
- **HTML Extraction & Fingerprinting** (Trafilatura & BeautifulSoup)
- **Incremental Indexing & Deduplication** (Cryptographic SHA-256 content hashes)
- **Inverted Text Index & BM25 Relevance Scoring** (OpenSearch)
- **Asynchronous Operator API & CLI Controls** (FastAPI)
- **Minimalist, High-Performance UI** (React 19 + TypeScript + Vite)

The system runs on standard hardware (≤16 GB RAM laptop) with ₹0 budget, conservative heap limits (OpenSearch heap strictly 512MB), and zero cloud/paid APIs.

```
                  ┌──────────────────────────────┐
                  │        React Frontend        │
                  │      (Vite / Port 3000)      │
                  └──────────────┬───────────────┘
                                 │ HTTP / JSON
                                 ▼
                  ┌──────────────────────────────┐
                  │       FastAPI Backend        │
                  │         (Port 8000)          │
                  └───┬──────────────────────┬───┘
                      │                      │
           Search API │         Operator API │
                      ▼                      ▼
           ┌─────────────────────┐   ┌─────────────────────────┐
           │     OpenSearch      │   │     Crawler Engine      │
           │     (Port 9200)     │   │  (Asynchronous Worker)  │
           │ Inverted BM25 Index │   └──┬─────────────┬────────┘
           └──────────▲──────────┘      │             │
                      │ Incremental     │ Outgoing    │ Leased Batches
                      │ Write           │ Links       ▼
                      │              ┌──┴──────────────────────┐
                      └──────────────┤   PostgreSQL Frontier   │
                                     │       (Port 5432)       │
                                     │  URL State & Lifecycle  │
                                     └─────────────────────────┘
```

---

## 2. Crawler & Frontier Architecture (Phase 2)

### 2.1 Frontier State Lifecycle
The crawl frontier manages a deterministic state machine:
```
                      ┌───────────────┐
                      │  DISCOVERED   │
                      └───────┬───────┘
                              ▼
                      ┌───────────────┐
                      │    QUEUED     │
                      └───────┬───────┘
                              │ Atomic Lease Claim
                              ▼
                      ┌───────────────┐
                      │   FETCHING    │
                      └───┬───────┬───┘
         Success          │       │ Failure
    ┌─────────────────────┘       └─────────────────────────┐
    ▼                                                       ▼
┌──────────────┐   Permanent Error / Max Retries     ┌──────────────┐
│   FETCHED    │   ─────────────────────────────►    │    FAILED    │
└──────┬───────┘                                     └──────────────┘
       │ Duplicate Hash                                     ▲
       ├─────────────────────► DUPLICATE                    │
       │ Blocked Directive                                  │
       ├─────────────────────► BLOCKED                      │
       │ Disallowed Scheme                                  │
       └─────────────────────► SKIPPED_POLICY               │
                                                            │
    Transient Failure (429, 5xx, Timeout)                   │
    ┌──────────────────────────────────────┐                │
    ▼                                      │ Exceeded       │
┌──────────────┐       Backoff Elapses     │ Max Attempts   │
│  RETRY_WAIT  ├───────────────────────────┴────────────────┘
└──────────────┘
```

### 2.2 Frontier Table Schema
- `url`: Original raw URL string.
- `normalized_url`: Canonicalized crawl identity (tracking stripped, default ports removed).
- `canonical_url`: Verified `<link rel="canonical">` or default normalized URL.
- `domain`, `scheme`: Target hostname and protocol.
- `discovery_source`: Referrer/parent URL for provenance.
- `depth`: Crawl distance from initial seeds (0-indexed).
- `status`: Active state in the frontier state machine.
- `priority`: Higher priority links processed first.
- `attempt_count`: Cumulative attempts for retry bounds.
- `next_fetch_at`: Schedulable timestamp for exponential backoff.
- `worker_id` & `lease_expires_at`: Atomic claim tokens. Unacknowledged leases are automatically reclaimed upon worker restart.
- `last_error` & `http_status`: Diagnostic trace.

---

## 3. Network Defense & SSRF Prevention

All outbound crawler requests pass through strict pre-flight checks:
1. **Forbidden Network Ranges**: Rejects private addresses (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`), CGNAT, documentation, and multicast.
2. **Cloud Metadata Shield**: Blocks `169.254.169.254` and `metadata.google.internal`.
3. **Pre-connection DNS Resolution**: Resolves target hostnames to concrete IP addresses and verifies every resolved candidate.
4. **Credential Stripping**: URLs containing embedded userinfo (`user:pass@host`) are strictly forbidden.
5. **Content Size Cap**: Hard ceiling at 2 MB (`MAX_RESPONSE_BYTES`) to prevent decompression attacks.
6. **MIME Whitelist**: Only `text/html` and `application/xhtml+xml` are parsed.

---

## 4. Robots.txt Compliance & Politeness

- **Parsing**: RFC-compliant directive evaluation via Protego.
- **Caching**: 24-hour cache TTL per domain.
- **Fail-safe Fallback**: Server errors (5xx) or connection dropouts are treated conservatively (crawling denied until the target recovers).
- **Per-Host Spacing**: Enforces minimum spacing (default: 1.5–2.0s) between successive requests to the same hostname, honoring `Crawl-delay` when specified.
- **Operator Switches**: Emergency global pause (`set_global_pause`) and domain-level blacklisting (`disable_domain`).

---

## 5. Content Extraction & Deduplication

- **Article Extraction**: `trafilatura` extracts clean readable body text, discarding navigation bars, headers, footers, and scripts, with BeautifulSoup fallback.
- **Fingerprinting**: SHA-256 hash of whitespace-collapsed text body.
- **Skip Redundant Writes**: If content hash matches the existing database record, OpenSearch reindexing is bypassed, saving cluster I/O.
- **Deterministic IDs**: `SHA-256(canonical_url)[:24]` guarantees idempotent document updates.
