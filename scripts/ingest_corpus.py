import argparse
import sys
import json
from pathlib import Path

# Add backend to sys.path so app modules import cleanly
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))

from app.core.logging import setup_logging
from app.repositories.opensearch_repo import get_opensearch_repo
from app.ingestion.pipeline import IngestionPipeline

setup_logging(level="INFO")


def run_ingestion(corpus_path: Path):
    if not corpus_path.exists():
        print(f"Error: Corpus file not found at {corpus_path}")
        sys.exit(1)

    with open(corpus_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"Loaded {len(docs)} documents from {corpus_path.name}")

    os_repo = get_opensearch_repo()
    if os_repo.ping():
        os_repo.ensure_index()
        print("Connected to OpenSearch and verified index mapping.")
    else:
        print("OpenSearch offline; running ingestion through resilient local store.")

    pipeline = IngestionPipeline(os_repo=os_repo)
    result = pipeline.ingest_corpus(docs, job_type="sample_corpus_ingestion")

    print("\n--- Ingestion Summary ---")
    print(f"Job ID:      {result['job_id']}")
    print(f"Total:       {result['total']}")
    print(f"Indexed:     {result['indexed']}")
    print(f"Duplicates:  {result['duplicates']}")
    print(f"Failed:      {result['failed']}")
    print("-------------------------\n")

    for item in result["results"]:
        status = item.get("status")
        url = item.get("url")
        if status == "indexed":
            print(f"  [OK] {item.get('title')} -> {url}")
        elif status == "duplicate":
            print(f"  [DUPLICATE] {url} matches {item.get('matched_url')}")
        else:
            print(f"  [FAILED] {url}: {item.get('error')}")

    return result


def main():
    parser = argparse.ArgumentParser(description="OM Search - Document Corpus Ingestion Tool")
    parser.add_argument(
        "--corpus",
        type=str,
        default=str(root_dir / "scripts" / "sample_corpus.json"),
        help="Path to JSON corpus file",
    )
    args = parser.parse_args()
    run_ingestion(Path(args.corpus))


if __name__ == "__main__":
    main()
