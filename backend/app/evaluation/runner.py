import time
from typing import Dict, Any, List, Callable, Optional
from datetime import datetime, timezone

from app.evaluation.dataset import EvaluationDataset, QueryCase
from app.evaluation.metrics import evaluate_query_ranking


class EvaluationRunner:
    """
    Executes an evaluation dataset against a search function and computes aggregate IR metrics.
    """

    def __init__(self, dataset: EvaluationDataset):
        self.dataset = dataset

    def run(
        self,
        search_fn: Callable[[str, int], List[str]],  # (query, size) -> List[doc_id]
        config_name: str = "default_configuration",
        k_values: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Run all query cases in the dataset and return per-query and aggregate metrics.
        search_fn should return a list of doc_ids in ranked order.
        """
        k_vals = k_values or [1, 3, 5, 10]
        start_time = time.perf_counter()

        per_query_results = []
        aggregates: Dict[str, float] = {
            "mrr": 0.0,
            "map": 0.0,
        }
        for k in k_vals:
            aggregates[f"p@{k}"] = 0.0
            aggregates[f"r@{k}"] = 0.0
            aggregates[f"ndcg@{k}"] = 0.0

        latencies_ms = []
        zero_result_queries = 0

        for case in self.dataset.cases:
            q_start = time.perf_counter()
            retrieved_ids = search_fn(case.query, max(k_vals))
            q_lat = (time.perf_counter() - q_start) * 1000.0
            latencies_ms.append(q_lat)

            if not retrieved_ids:
                zero_result_queries += 1

            # Map retrieved URLs/IDs to canonical IDs matching dataset keys
            from app.ingestion.normalizer import normalize_url, compute_url_id
            canonical_retrieved_ids = []
            for rid in retrieved_ids:
                if rid in case.relevant_docs:
                    canonical_retrieved_ids.append(rid)
                elif rid.startswith("http://") or rid.startswith("https://"):
                    try:
                        h_id = compute_url_id(normalize_url(rid))
                        canonical_retrieved_ids.append(h_id)
                    except Exception:
                        canonical_retrieved_ids.append(rid)
                else:
                    canonical_retrieved_ids.append(rid)

            query_metrics = evaluate_query_ranking(
                retrieved_ids=canonical_retrieved_ids,
                relevant_grades=case.relevant_docs,
                k_values=k_vals,
            )

            # Record individual query run
            per_query_results.append({
                "query_id": case.query_id,
                "query": case.query,
                "intent": case.intent,
                "retrieved_count": len(retrieved_ids),
                "latency_ms": round(q_lat, 2),
                "metrics": query_metrics,
            })

            # Accumulate for macro-average
            for m_key, m_val in query_metrics.items():
                aggregates[m_key] = aggregates.get(m_key, 0.0) + m_val

        total_queries = len(self.dataset.cases)
        total_time_ms = (time.perf_counter() - start_time) * 1000.0

        if total_queries > 0:
            for k in aggregates:
                aggregates[k] = round(aggregates[k] / total_queries, 4)

        latencies_ms.sort()
        p50_lat = latencies_ms[len(latencies_ms) // 2] if latencies_ms else 0.0
        p95_lat = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0

        return {
            "dataset_version": self.dataset.version,
            "config_name": config_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_queries": total_queries,
            "zero_result_queries": zero_result_queries,
            "zero_result_rate": round(zero_result_queries / max(1, total_queries), 4),
            "macro_aggregates": aggregates,
            "latency": {
                "total_ms": round(total_time_ms, 2),
                "median_ms": round(p50_lat, 2),
                "p95_ms": round(p95_lat, 2),
            },
            "queries": per_query_results,
        }
