import argparse
import json
import sys
from pathlib import Path

# Add backend to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))

from app.evaluation.dataset import get_default_evaluation_dataset
from app.evaluation.runner import EvaluationRunner
from app.evaluation.ablation import AblationExperimentHarness, get_ablation_configurations
from app.services.search_service import SearchService
from app.ranking.config import RankingConfig


def run_single_eval(output_path: Path):
    print("Loading default Phase 3 benchmark dataset...")
    dataset = get_default_evaluation_dataset()
    print(f"Loaded {len(dataset.cases)} evaluation queries.")

    service = SearchService()

    def search_fn(query: str, size: int):
        resp = service.search(query=query, size=size)
        return [r.id for r in resp.results]

    runner = EvaluationRunner(dataset)
    results = runner.run(search_fn, config_name="default_production_v3")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n--- Evaluation Summary ---")
    print(f"Config:          {results['config_name']}")
    print(f"Total Queries:   {results['total_queries']}")
    print(f"Zero Result Qs:  {results['zero_result_queries']}")
    print(f"MRR:             {results['macro_aggregates'].get('mrr', 0.0):.4f}")
    print(f"MAP:             {results['macro_aggregates'].get('map', 0.0):.4f}")
    print(f"P@1:             {results['macro_aggregates'].get('p@1', 0.0):.4f}")
    print(f"P@3:             {results['macro_aggregates'].get('p@3', 0.0):.4f}")
    print(f"NDCG@10:         {results['macro_aggregates'].get('ndcg@10', 0.0):.4f}")
    print(f"Median Latency:  {results['latency']['median_ms']} ms")
    print("--------------------------\n")
    print(f"Saved full report to {output_path}")


def run_ablation_experiments(output_path: Path):
    print("Initializing Phase 3 Ablation Experiment Suite...")
    dataset = get_default_evaluation_dataset()
    harness = AblationExperimentHarness(dataset)

    def search_fn_factory(config: RankingConfig):
        srv = SearchService(ranking_config=config)
        def search_fn(query: str, size: int):
            resp = srv.search(query=query, size=size)
            return [r.id for r in resp.results]
        return search_fn

    ablation_results = harness.run_ablation(search_fn_factory)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ablation_results, f, indent=2)

    print("\n======================= ABLATION BENCHMARK RESULTS =======================")
    print(f"{'Configuration':<28} | {'MRR':<6} | {'Δ MRR':<7} | {'NDCG@10':<8} | {'Δ NDCG':<8} | {'Zero %':<6}")
    print("-" * 75)

    for item in ablation_results["comparison_summary"]:
        cfg = item["config"]
        mrr = f"{item['mrr']:.4f}"
        d_mrr = f"{item['mrr_delta']:+.4f}" if item['mrr_delta'] != 0 else "0.0000"
        ndcg = f"{item['ndcg@10']:.4f}"
        d_ndcg = f"{item['ndcg_delta']:+.4f}" if item['ndcg_delta'] != 0 else "0.0000"
        zero = f"{item['zero_result_rate']:.2%}"
        print(f"{cfg:<28} | {mrr:<6} | {d_mrr:<7} | {ndcg:<8} | {d_ndcg:<8} | {zero:<6}")

    print("==========================================================================\n")
    print(f"Saved ablation report to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="OM Search - Phase 3 Ranking Evaluation & Ablation CLI")
    subparsers = parser.add_subparsers(dest="command")

    eval_cmd = subparsers.add_parser("eval", help="Run evaluation on active ranking configuration")
    eval_cmd.add_argument("--out", type=str, default="docs/experiments/evaluation_report.json")

    ablation_cmd = subparsers.add_parser("ablation", help="Run ablation experiment across all configurations")
    ablation_cmd.add_argument("--out", type=str, default="docs/experiments/ablation_report.json")

    args = parser.parse_args()

    if args.command == "eval":
        run_single_eval(Path(args.out))
    elif args.command == "ablation":
        run_ablation_experiments(Path(args.out))
    else:
        # Default to ablation if no command provided
        run_ablation_experiments(Path("docs/experiments/ablation_report.json"))


if __name__ == "__main__":
    main()
