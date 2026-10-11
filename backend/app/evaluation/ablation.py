import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.ranking.config import RankingConfig
from app.evaluation.dataset import EvaluationDataset, get_default_evaluation_dataset
from app.evaluation.runner import EvaluationRunner

logger = logging.getLogger(__name__)


def get_ablation_configurations() -> Dict[str, RankingConfig]:
    """
    Returns the standard set of configurations for ablation testing.
    """
    return {
        # A. Raw BM25 baseline (no authority, no freshness, no quality weight)
        "A_baseline_bm25": RankingConfig(
            version="ablation_A",
            weight_bm25=1.0,
            weight_title_coverage=0.0,
            weight_authority=0.0,
            weight_freshness=0.0,
            weight_quality=0.0,
            enable_phrase_boost=False,
            enable_synonyms=False,
            enable_authority=False,
            enable_freshness=False,
            enable_quality_filter=False,
            enable_near_dedup=False,
        ),
        # B. BM25 plus title & phrase boosts
        "B_bm25_plus_title_phrase": RankingConfig(
            version="ablation_B",
            weight_bm25=0.70,
            weight_title_coverage=0.30,
            weight_authority=0.0,
            weight_freshness=0.0,
            weight_quality=0.0,
            enable_phrase_boost=True,
            enable_synonyms=True,
            enable_authority=False,
            enable_freshness=False,
            enable_quality_filter=False,
            enable_near_dedup=False,
        ),
        # C. BM25 plus query intent & freshness
        "C_bm25_plus_freshness": RankingConfig(
            version="ablation_C",
            weight_bm25=0.60,
            weight_title_coverage=0.20,
            weight_authority=0.0,
            weight_freshness=0.20,
            weight_quality=0.0,
            enable_phrase_boost=True,
            enable_synonyms=True,
            enable_authority=False,
            enable_freshness=True,
            enable_quality_filter=False,
            enable_near_dedup=False,
        ),
        # D. BM25 plus link authority (PageRank)
        "D_bm25_plus_authority": RankingConfig(
            version="ablation_D",
            weight_bm25=0.60,
            weight_title_coverage=0.20,
            weight_authority=0.20,
            weight_freshness=0.0,
            weight_quality=0.0,
            enable_phrase_boost=True,
            enable_synonyms=True,
            enable_authority=True,
            enable_freshness=False,
            enable_quality_filter=False,
            enable_near_dedup=False,
        ),
        # E. BM25 plus quality and duplicate controls
        "E_bm25_plus_quality_dedup": RankingConfig(
            version="ablation_E",
            weight_bm25=0.60,
            weight_title_coverage=0.20,
            weight_authority=0.0,
            weight_freshness=0.0,
            weight_quality=0.20,
            enable_phrase_boost=True,
            enable_synonyms=True,
            enable_authority=False,
            enable_freshness=False,
            enable_quality_filter=True,
            enable_near_dedup=True,
        ),
        # G. Full enabled feature set
        "G_full_ranking_pipeline": RankingConfig(
            version="ablation_G",
            weight_bm25=0.55,
            weight_title_coverage=0.15,
            weight_authority=0.10,
            weight_freshness=0.10,
            weight_quality=0.10,
            enable_phrase_boost=True,
            enable_synonyms=True,
            enable_authority=True,
            enable_freshness=True,
            enable_quality_filter=True,
            enable_near_dedup=True,
        ),
    }


class AblationExperimentHarness:
    """
    Executes a side-by-side ablation experiment comparing multiple ranking configurations
    on the exact same benchmark dataset.
    """

    def __init__(self, dataset: Optional[EvaluationDataset] = None):
        self.dataset = dataset or get_default_evaluation_dataset()
        self.runner = EvaluationRunner(self.dataset)

    def run_ablation(
        self,
        search_fn_factory,  # Callable[[RankingConfig], Callable[[str, int], List[str]]]
        configs: Optional[Dict[str, RankingConfig]] = None,
    ) -> Dict[str, Any]:
        cfg_dict = configs or get_ablation_configurations()
        results: Dict[str, Any] = {}

        for name, config in cfg_dict.items():
            logger.info("Executing ablation configuration: %s", name)
            search_fn = search_fn_factory(config)
            run_result = self.runner.run(search_fn, config_name=name)
            results[name] = run_result

        # Compute delta comparisons against baseline A
        baseline_res = results.get("A_baseline_bm25", {})
        baseline_mrr = baseline_res.get("macro_aggregates", {}).get("mrr", 0.0)
        baseline_ndcg = baseline_res.get("macro_aggregates", {}).get("ndcg@10", 0.0)

        comparison = []
        for name, res in results.items():
            mrr = res.get("macro_aggregates", {}).get("mrr", 0.0)
            ndcg = res.get("macro_aggregates", {}).get("ndcg@10", 0.0)
            comparison.append({
                "config": name,
                "mrr": mrr,
                "mrr_delta": round(mrr - baseline_mrr, 4),
                "ndcg@10": ndcg,
                "ndcg_delta": round(ndcg - baseline_ndcg, 4),
                "zero_result_rate": res.get("zero_result_rate", 0.0),
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dataset_version": self.dataset.version,
            "total_queries": len(self.dataset.cases),
            "comparison_summary": comparison,
            "runs": results,
        }
