# OM Search — Phase 3: Operational Guide

This document describes operations, index maintenance, PageRank graph recalculations, evaluation routines, and monitoring for OM Search.

---

## 1. Running Offline Link Graph & PageRank Recomputations

During normal crawling (Phase 2), discovered hyperlinks are recorded in the PostgreSQL/SQLite `page_links` table. To compute and persist updated PageRank authority scores across the crawled corpus:

### Programmatic Invocation
```python
from crawler.om_crawler.link_graph import LinkGraphManager

manager = LinkGraphManager()
# Computes PageRank with damping=0.85, max_iter=50, tolerance=1e-6
results = manager.compute_and_save_pagerank(damping=0.85, max_iter=50)

print(f"Computed PageRank across {results['nodes']} pages.")
print(f"Iterations: {results['iterations']}, Converged: {results['converged']}")
```

### Direct Database Queries
To inspect top pages by link authority:
```sql
SELECT u.canonical_url, a.pagerank, a.in_degree, a.out_degree
FROM page_authority a
JOIN crawled_urls u ON u.id = a.url_id
ORDER BY a.pagerank DESC
LIMIT 10;
```

---

## 2. Ranking Configuration Versioning & Rollback

Ranking weights and toggles are managed via `RankingConfig`:
```python
from app.ranking.config import RankingConfig

# Custom or experimental configuration
experimental_cfg = RankingConfig(
    version="3.1.0-exp",
    weight_bm25=0.50,
    weight_title_coverage=0.20,
    weight_authority=0.15,
    weight_freshness=0.05,
    weight_quality=0.10,
    enable_phrase_boost=True,
)
```

To rollback to baseline BM25 behavior in production without deploying code, set feature weights to zero:
```python
baseline_cfg = RankingConfig(
    version="3.0.0-rollback",
    weight_bm25=1.0,
    weight_title_coverage=0.0,
    weight_authority=0.0,
    weight_freshness=0.0,
    weight_quality=0.0,
)
```

---

## 3. Running Continuous Evaluation & Benchmark Suite

### Test Execution
Run the full test suite across all 74 unit, integration, and crawler tests:
```powershell
.\.venv\Scripts\pytest backend/tests/ -v
```

### Benchmark Evaluation CLI
Run evaluation on active production ranking:
```powershell
python scripts/evaluate_ranking.py eval --out docs/experiments/evaluation_report.json
```

Run full ablation comparison:
```powershell
python scripts/evaluate_ranking.py ablation --out docs/experiments/ablation_report.json
```

---

## 4. Search API Endpoint with Explanations

To inspect why a document ranks in its position, call `/api/v1/search` with `explain=true`:
```bash
curl "http://localhost:8000/api/v1/search?q=fastapi&explain=true"
```
The response will include `explanation` reasons and raw normalized `features` for every hit.
