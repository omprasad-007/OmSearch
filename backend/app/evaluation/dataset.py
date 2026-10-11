import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.ingestion.normalizer import normalize_url, compute_url_id


@dataclass
class QueryCase:
    query_id: str
    query: str
    intent: str  # informational, navigational, technical, freshness, general
    relevant_docs: Dict[str, int]  # doc_id or canonical_url -> grade (0 to 3)
    notes: Optional[str] = None
    provenance: str = "curated_ground_truth"


@dataclass
class EvaluationDataset:
    version: str
    description: str
    cases: List[QueryCase] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "description": self.description,
            "cases": [asdict(c) for c in self.cases],
        }

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: Path | str) -> "EvaluationDataset":
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        cases = [
            QueryCase(
                query_id=c["query_id"],
                query=c["query"],
                intent=c.get("intent", "general"),
                relevant_docs=c.get("relevant_docs", {}),
                notes=c.get("notes"),
                provenance=c.get("provenance", "curated_ground_truth"),
            )
            for c in data.get("cases", [])
        ]
        return cls(
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            cases=cases,
        )


def get_default_evaluation_dataset() -> EvaluationDataset:
    """
    Creates the default, version-controlled Phase 3 benchmark dataset.
    Relevance scale:
    3: Highly relevant (Primary target / Definitive documentation)
    2: Relevant (Substantive content match)
    1: Marginally relevant (Peripheral mention)
    0: Irrelevant
    """
    # Deterministic IDs for sample corpus URLs
    u_py = compute_url_id(normalize_url("https://docs.python.org/3/tutorial/introduction.html"))
    u_os = compute_url_id(normalize_url("https://opensearch.org/docs/latest/getting-started/overview/"))
    u_pg = compute_url_id(normalize_url("https://www.postgresql.org/docs/current/intro-whatis.html"))
    u_fa = compute_url_id(normalize_url("https://fastapi.tiangolo.com/tutorial/first-steps/"))
    u_re = compute_url_id(normalize_url("https://react.dev/learn"))
    u_sq = compute_url_id(normalize_url("https://www.sqlite.org/about.html"))
    u_http = compute_url_id(normalize_url("https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview"))
    u_stat = compute_url_id(normalize_url("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status"))

    cases = [
        # Technical & Informational queries
        QueryCase(
            query_id="q01_python_intro",
            query="python programming language introduction",
            intent="informational",
            relevant_docs={u_py: 3, u_fa: 1, u_os: 0, u_sq: 0},
            notes="Should heavily rank the Python introduction tutorial #1.",
        ),
        QueryCase(
            query_id="q02_fastapi_web",
            query="fastapi python web framework",
            intent="technical",
            relevant_docs={u_fa: 3, u_py: 1, u_pg: 0, u_re: 0},
            notes="FastAPI first steps is the definitive answer.",
        ),
        QueryCase(
            query_id="q03_opensearch_bm25",
            query="opensearch distributed search engine bm25",
            intent="technical",
            relevant_docs={u_os: 3, u_pg: 0, u_sq: 0, u_py: 0},
            notes="OpenSearch overview documentation contains BM25 & search engine text.",
        ),
        QueryCase(
            query_id="q04_postgresql_acid",
            query="postgresql object relational database acid",
            intent="technical",
            relevant_docs={u_pg: 3, u_sq: 1, u_os: 0, u_py: 0},
            notes="PostgreSQL whatis covers ACID and object-relational engine; SQLite is marginally relevant.",
        ),
        QueryCase(
            query_id="q05_react_components",
            query="react user interfaces components state",
            intent="technical",
            relevant_docs={u_re: 3, u_fa: 0, u_py: 0, u_os: 0},
            notes="React Quick Start covers components, JSX, and state.",
        ),
        QueryCase(
            query_id="q06_sqlite_serverless",
            query="sqlite serverless embedded database engine",
            intent="technical",
            relevant_docs={u_sq: 3, u_pg: 1, u_os: 0, u_py: 0},
            notes="SQLite About page covers serverless self-contained database.",
        ),
        QueryCase(
            query_id="q07_http_status_codes",
            query="http response status codes",
            intent="informational",
            relevant_docs={u_stat: 3, u_http: 2, u_fa: 0, u_py: 0},
            notes="MDN Status codes is #1 (grade 3), MDN HTTP Overview is #2 (grade 2).",
        ),
        QueryCase(
            query_id="q08_http_protocol_overview",
            query="hypertext transfer protocol http overview",
            intent="informational",
            relevant_docs={u_http: 3, u_stat: 1, u_pg: 0, u_sq: 0},
            notes="MDN HTTP Overview is primary.",
        ),
        # Navigational queries
        QueryCase(
            query_id="q09_nav_python",
            query="python documentation",
            intent="navigational",
            relevant_docs={u_py: 3, u_fa: 0, u_re: 0},
            notes="Navigational target for Python.",
        ),
        QueryCase(
            query_id="q10_nav_fastapi",
            query="fastapi documentation",
            intent="navigational",
            relevant_docs={u_fa: 3, u_py: 0, u_pg: 0},
            notes="Navigational target for FastAPI.",
        ),
        # Freshness / Recency queries
        QueryCase(
            query_id="q11_fresh_updates",
            query="fastapi latest updates release",
            intent="freshness",
            relevant_docs={u_fa: 3, u_py: 1, u_http: 0},
            notes="Freshness-sensitive query.",
        ),
    ]

    return EvaluationDataset(
        version="1.0.0",
        description="OM Search Core Benchmark Dataset (Phase 3 Starter Benchmark)",
        cases=cases,
    )
