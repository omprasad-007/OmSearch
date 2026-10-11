# OM Search Engine — Future Roadmap (Phases 2–5)

This roadmap outlines the evolution of OM Search from Phase 1 (Engine Foundation) into a distributed, web-scale search engine.

---

## Phase 2: Controlled Web Crawler & Politeness Engine — [COMPLETED]
- **Persistent PostgreSQL / SQLite URL Frontier**:
  - Frontier lifecycle states: `DISCOVERED`, `QUEUED`, `FETCHING`, `FETCHED`, `SKIPPED_POLICY`, `RETRY_WAIT`, `FAILED`, `BLOCKED`, `DUPLICATE`.
  - Atomic worker leases with `lease_expires_at` and automatic reclamation of orphaned worker jobs.
  - Exponential backoff with random jitter for transient errors (HTTP 429, 503, timeouts).
- **Network Safety & Anti-SSRF Security**:
  - Strict IP validation: blocks private RFC 1918, loopback `127.0.0.0/8`, link-local `169.254.0.0/16`, cloud metadata `169.254.169.254`, IPv6, multicast.
  - DNS resolution time verification defending against rebinding and redirect-based SSRF.
  - Embedded credentials blocked; HTTP/HTTPS schemes only; MIME whitelist (HTML/XHTML); 2MB response size limit.
- **Protego-based Robots.txt & Politeness**:
  - Live robots.txt caching (24h TTL) and compliance with Google/RFC directive precedence (`Disallow`, `Allow`, `Crawl-delay`).
  - Conservative error handling (fail-closed on 5xx or server errors).
  - Emergency global pause (`robots_mgr.set_global_pause(True)`) and per-domain disable switches.
  - Per-host rate limiting (default 1.5–2s delay, 1 concurrent request per host).
- **HTML Extraction & Deduplication Pipeline**:
  - Primary main text extraction via Trafilatura with resilient fallback to BeautifulSoup.
  - Title, meta description, canonical URL validation, language detection, and outgoing link extraction.
  - Content fingerprinting via SHA-256: prevents duplicate OpenSearch index writes when content is unchanged.
- **Operator API & CLI Controls**:
  - REST endpoints: `/api/v1/crawl/jobs`, `/pause`, `/resume`, `/cancel`, `/stats`, `/failures`.
  - Operator CLI: `python scripts/run_crawler.py [start|stats|failures|reset-leases]`.

---

## Phase 3: Ranking Intelligence, Relevance, Link Analysis, Anti-Spam & Evaluation — [COMPLETED]
- **Two-Stage Retrieval & Multi-Feature Reranking**:
  - Stage 1: Candidate generation retrieving top-50 documents via tuned OpenSearch BM25 (`title^3.0`, `snippet^1.5`, `content^1.0`).
  - Stage 2: Feature-weighted reranking combining normalized BM25, title coverage, exact title matches, phrase matches, PageRank authority, query-intent gated freshness, content quality, and anti-spam penalties.
  - Runtime explainability: `/api/v1/search?explain=true` with score component breakdown and human-readable explanation sentences.
- **Link Graph & Offline PageRank Authority**:
  - `page_links` directed edge table and `page_authority` table.
  - Deterministic PageRank calculator with power iteration, uniform dangling node mass redistribution, damping ($0.85$), and convergence check ($\epsilon=10^{-6}$).
  - Log-scaled authority normalization for bounded integration with search scoring.
- **Query Understanding Subsystem**:
  - Unicode NFKC normalization, quoted phrase extraction (`"..."`), and punctuation cleaning.
  - Technical identifier preservation (CamelCase, snake_case, dotted names, URLs).
  - Rule-based intent classification: `informational`, `navigational`, `technical`, `freshness`, `general`.
  - Curated technical synonym expansion (`py`/`python`, `postgres`/`postgresql`, `db`/`database`).
  - Conservative Levenshtein-based spelling suggestion.
- **Content Quality & Anti-Spam Controls**:
  - Length-based quality scoring saturating at ~60 words with brevity penalty for stubs (< 8 words).
  - Keyword stuffing detection (term frequency ratio > 18%) and title repetition detection.
  - Word 3-gram shingling and Jaccard near-duplicate suppression ($\ge 0.70$) suppressing mirror domains.
- **Rigorous Information Retrieval Evaluation**:
  - Formal mathematical implementations of Precision@k, Recall@k, Reciprocal Rank, Average Precision, DCG@k, IDCG@k, and NDCG@k with hand-calculated unit test verification.
  - Version-controlled benchmark dataset (`EvaluationDataset`, `QueryCase`) spanning technical, informational, navigational, and freshness intents.
  - Evaluation CLI (`scripts/evaluate_ranking.py [eval|ablation]`) and ablation harness running side-by-side comparisons of 6 standard configurations.

---

## Phase 4: Search Evaluation & Quality Metrics
- **Offline Evaluation (TREC / Cranfield Style)**:
  - Benchmark query sets with ground truth relevance judgments.
  - Automated calculation of NDCG@10, Mean Reciprocal Rank (MRR), and Precision@k.
- **Online Evaluation & Telemetry**:
  - Zero-result query tracking and spelling correction (Levenshtein / n-gram distance).
  - Anonymized click-through rate (CTR) and dwell time telemetry without user tracking.
- **Continuous Regressions**:
  - CI test suite measuring search ranking regressions against frozen sample indices.

---

## Phase 5: Distributed Scaling & High Availability
- **Distributed Inverted Indexing**:
  - Sharding strategies by document ID hash (`murmur3`) or domain partitioning.
  - Replica shards for failover and read load-balancing.
- **Tiered Document Storage**:
  - Hot tier: SSD-backed OpenSearch indices for active queries.
  - Warm/Cold tier: Object storage (S3 / MinIO) for raw compressed WARC / HTML archives.
- **Observability & Health Monitoring**:
  - Prometheus metrics exporter for crawler throughput (pages/sec), fetch latencies, and OpenSearch query timings.
  - Grafana dashboards displaying crawl frontier size, memory utilization, and cache hit ratios.
