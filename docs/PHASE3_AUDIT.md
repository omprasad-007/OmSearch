# OM Search — Phase 3 Architecture Audit & Implementation Plan

**Date**: October 2026  
**Auditor**: OM Search Core IR & Infrastructure Team  
**Scope**: Transition from Phase 2 (Independent Web Crawler & Frontier) to Phase 3 (Ranking Intelligence, Link Analysis, Anti-Spam, and Evaluation)

---

## 1. Executive Summary & Existing Baseline

An audit of the OM Search repository was conducted prior to Phase 3 implementation. The codebase possesses a solid Phase 1 and Phase 2 foundation:

- **Backend**: FastAPI with modular routers, Pydantic v2 schemas, PostgreSQL with seamless SQLite local fallback, and OpenSearch with an offline fallback document store.
- **Frontend**: React 19 + TypeScript + Vite UI with instant suggestions, stats modal, and responsive search results.
- **Crawler**: Scrapy-inspired polite crawler with Protego-based robots.txt parsing, strict SSRF/network security filters, SHA-256 content deduplication, Trafilatura HTML extraction, and persistent database frontier (`DISCOVERED` -> `QUEUED` -> `FETCHING` -> `FETCHED` / `RETRY_WAIT`).
- **Test Baseline**: 
  - **Backend (Pytest)**: **52 passed** (100% pass rate).
  - **Frontend (Vitest)**: **4 passed** (100% pass rate).

---

## 2. Component Audits

### 2.1 Search API & Contracts
- **Endpoints**:
  - `GET /api/v1/search?q={query}&page={page}&size={size}&language={lang}&domain={domain}`
  - `GET /api/v1/suggestions?q={prefix}`
  - `GET /api/v1/search/stats`
  - `GET /api/v1/health`
- **Current Model**: `SearchResponse` containing `SearchResultItem` (id, url, title, snippet, score, published_at, indexed_at, domain, language).
- **Ranking Logic**: `build_bm25_search_query` in `backend/app/ranking/bm25.py` uses multi-field matching with field boosts (title^3.0, snippet^1.5, content^1.0) and phrase matching.
- **Phase 3 Gap**: Current scoring relies solely on Lucene/OpenSearch BM25; it lacks two-stage retrieval + reranking, query intent classification, authority (PageRank), query-sensitive freshness, spam/quality filtering, near-duplicate suppression, and explanation metadata.

### 2.2 OpenSearch Index Mapping & Analyzers
- **Index**: `om_documents_v1` (alias `om_documents`).
- **Analyzers**:
  - `om_english_analyzer`: standard tokenizer, lowercase, english_stop, english_stemmer.
  - `om_suggest_analyzer`: edge_ngram filter (min 2, max 15) for title autocompletion.
- **Fields**: `id`, `url`, `canonical_url`, `domain`, `title` (standard + english + keyword + suggest), `content` (standard + english), `snippet`, `language`, `published_at`, `fetched_at`, `indexed_at`, `content_hash`, `http_status`, `document_type`.
- **Phase 3 Extension**: Support `pagerank` (float), `quality_score` (float), `spam_score` (float), and `cluster_id` (keyword) without breaking existing schemas.

### 2.3 Database Schema & Persistence
- **Existing Tables**:
  - `urls`: Frontier lifecycle, canonical URLs, domains, schemes, depth, priority, attempt_count, `content_hash`, `discovery_source` (referrer).
  - `crawl_jobs`: State machine, counters, configs.
  - `document_lifecycle`: Detailed audit trail of fetch/dedup/indexing decisions.
- **Phase 3 Gap**:
  - Need dedicated `page_links` table for directed hyperlink graph construction: `(source_url, target_url, source_domain, target_domain, anchor_text)`.
  - Need `page_authority` table for versioned PageRank computation snapshots: `(canonical_url, pagerank, in_degree, out_degree, snapshot_version)`.

### 2.4 HTML Content Extraction & Provenance
- `HTMLExtractor` (`crawler/om_crawler/extractor.py`) already extracts:
  - `title`, `main_text` (via Trafilatura/BeautifulSoup), `meta_description`, `canonical_url`, `language`, `published_at` (via htmldate/metadata), and `outgoing_links`.
- In Phase 2, outgoing links are enqueued into the frontier. In Phase 3, these links are also persisted into `page_links` for graph analysis.

---

## 3. Phase 3 Architecture Design

```
User Query
    │
    ▼
[ Query Processor ] ──> Trimming, Unicode normalization, Punctuation handling,
    │                   Identifier preservation, Rule-based Intent Classifier
    │                   (Navigational, Informational, Freshness, Technical)
    ▼
[ Stage 1: Candidate Generation ] ──> OpenSearch Lexical (BM25 + Field Boosts + Synonyms)
    │                                 Optional: Vector k-NN (Feature Flagged)
    │                                 Pool size: top N candidates (default 50)
    ▼
[ Stage 2: Feature Extraction ] ────> Extract per-candidate feature vector:
    │                                 1. BM25 score
    │                                 2. Title match & phrase match boost
    │                                 3. Heading / path coverage
    │                                 4. PageRank (link authority)
    │                                 5. Query-dependent freshness decay
    │                                 6. Quality score (text-to-boilerplate ratio, length)
    │                                 7. Spam score & penalty (keyword stuffing, repetition)
    ▼
[ Score Combination & Safeguards ] ─> Log-transforms, min-max clipping, missing-feature handling,
    │                                 Policy safeguards (spam gate, dead-link exclusion)
    ▼
[ Candidate Deduplication ] ────────> Near-duplicate suppression (SimHash/Shingle matching)
    │
    ▼
[ Result Presentation ] ────────────> Safe text escaping, snippet highlighting,
                                      Deterministic tie-breaking, Diagnostic ranking explanation
```

---

## 4. Evaluation Strategy & Benchmark Dataset

### 4.1 Graded Relevance Scale
- **0**: Irrelevant
- **1**: Marginally Relevant
- **2**: Relevant
- **3**: Highly Relevant (Definitive answer / Primary documentation)

### 4.2 Benchmark Dataset (`evaluation/relevance_dataset.json`)
A curated, versioned dataset comprising diverse query intents:
- Technical Queries (e.g., `"python list comprehension"`, `"fastapi async endpoints"`, `"sqlite acid properties"`).
- Navigational Queries (e.g., `"python documentation"`, `"opensearch home"`).
- Informational Queries (e.g., `"what is inverted index"`, `"http status codes meaning"`).
- Freshness-sensitive Queries (e.g., `"opensearch 2.18 release"`, `"recent python changes"`).

### 4.3 Information Retrieval Metrics
Independent, mathematically verified IR metrics implemented in `evaluation/metrics.py`:
- **Precision@k** ($k \in \{1, 3, 5, 10\}$)
- **Recall@k**
- **MRR (Mean Reciprocal Rank)**
- **MAP (Mean Average Precision)**
- **NDCG@k (Normalized Discounted Cumulative Gain)** with $\text{IDCG}$ calculation and discount $\log_2(i + 1)$.
- **Zero-result rate** & **Duplicate result rate**.

### 4.4 Ablation Harness (`evaluation/ablation_runner.py`)
Compares 7 distinct configurations on the exact same dataset:
1. `baseline_bm25`: Raw lexical BM25 baseline.
2. `bm25_plus_fields`: BM25 with title, phrase, and identifier boosts.
3. `bm25_plus_intent_freshness`: With query intent classification and temporal decay.
4. `bm25_plus_authority`: With offline PageRank authority.
5. `bm25_plus_quality_dedup`: With spam resistance and near-duplicate suppression.
6. `full_ranking_pipeline`: All features combined.
7. `optional_hybrid`: Lexical + semantic embeddings (when feature enabled).

---

## 5. Implementation Roadmap & File Changes

| Module / Component | Target Files | Purpose |
|---|---|---|
| **Database & Graph Tables** | `backend/app/repositories/database.py`, `infrastructure/postgres/init.sql` | Add `PageLink` and `PageAuthority` models |
| **Link Graph & PageRank** | `crawler/om_crawler/link_graph.py`, `crawler/om_crawler/pagerank.py` | Directed graph builder and deterministic PageRank solver |
| **Query Understanding** | `backend/app/ranking/query_processor.py` | Normalization, intent classifier, technical identifier preservation |
| **Synonyms & Config** | `backend/app/ranking/synonyms.py`, `backend/app/ranking/config.py` | Curated synonym groups, versioned ranking weights configuration |
| **Feature Extraction & Scorer**| `backend/app/ranking/features.py`, `backend/app/ranking/scorer.py` | Multi-feature extraction, normalization, and score combiner |
| **Quality & Anti-Spam** | `backend/app/ranking/quality.py`, `backend/app/ranking/deduplication.py` | Text quality metrics, keyword stuffing detector, MinHash near-dedup |
| **Freshness Engine** | `backend/app/ranking/freshness.py` | Exponential decay with query-intent gating |
| **Two-Stage Search Service** | `backend/app/services/search_service.py` | Candidate generation -> Feature reranking -> Presentation |
| **Explanation & Diagnostics**| `backend/app/schemas/search.py`, `backend/app/api/v1/router.py` | Diagnostic search explanations (`explain=true`) |
| **Evaluation & Metrics** | `backend/app/evaluation/metrics.py`, `backend/app/evaluation/dataset.py`, `backend/app/evaluation/runner.py` | Precision, MRR, MAP, NDCG, and ablation suite |
| **Tests** | `backend/tests/test_ranking_*.py`, `backend/tests/test_evaluation_*.py`, `backend/tests/test_link_graph.py` | Comprehensive unit and integration test coverage |

---

## 6. Acceptance Gates
- **Gate A (Compatibility)**: All 52 existing tests pass with 0 regressions.
- **Gate B (Ranking)**: Two-stage retrieval + reranker is fully functional and configurable.
- **Gate C (Evaluation)**: Hand-calculated metric tests pass; ablation suite runs and generates versioned JSON reports.
- **Gate D (Security)**: XSS/injection safe, bounded regexes, untrusted content sanitized, safe fallback if ranking features fail.
- **Gate E (Documentation)**: Complete architectural, feature, and operational documentation in `docs/`.
