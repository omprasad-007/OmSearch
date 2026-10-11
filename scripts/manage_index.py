import argparse
import sys
import json
from pathlib import Path

# Add backend to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))

from app.core.config import get_settings
from app.repositories.opensearch_repo import get_opensearch_repo
from app.repositories.opensearch_mapping import OPENSEARCH_INDEX_MAPPING


def main():
    parser = argparse.ArgumentParser(description="OM Search - OpenSearch Index Management Tool")
    parser.add_argument("action", choices=["create", "delete", "recreate", "status", "mapping"], help="Action to perform")
    parser.add_argument("--index", default=None, help="Index name override")
    parser.add_argument("--alias", default=None, help="Alias name override")
    args = parser.parse_args()

    settings = get_settings()
    repo = get_opensearch_repo()
    index_name = args.index or settings.OPENSEARCH_INDEX_NAME
    alias_name = args.alias or settings.OPENSEARCH_INDEX_ALIAS

    print(f"OM Search Index Manager: Target index='{index_name}', alias='{alias_name}'")

    if not repo.ping():
        print(f"Warning: OpenSearch not reachable at {settings.opensearch_url}")
        if args.action in ("status", "mapping"):
            print(json.dumps(OPENSEARCH_INDEX_MAPPING, indent=2))
            return
        sys.exit(1)

    client = repo.get_client()

    if args.action == "create":
        if client.indices.exists(index=index_name):
            print(f"Index '{index_name}' already exists.")
        else:
            client.indices.create(index=index_name, body=OPENSEARCH_INDEX_MAPPING)
            print(f"Successfully created index '{index_name}' with OM Search mapping.")
            if alias_name:
                client.indices.put_alias(index=index_name, name=alias_name)
                print(f"Successfully created alias '{alias_name}' -> '{index_name}'.")

    elif args.action == "delete":
        if client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
            print(f"Successfully deleted index '{index_name}'.")
        else:
            print(f"Index '{index_name}' does not exist.")

    elif args.action == "recreate":
        if client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
            print(f"Deleted existing index '{index_name}'.")
        client.indices.create(index=index_name, body=OPENSEARCH_INDEX_MAPPING)
        print(f"Created fresh index '{index_name}'.")
        if alias_name:
            client.indices.put_alias(index=index_name, name=alias_name)
            print(f"Re-linked alias '{alias_name}' -> '{index_name}'.")

    elif args.action == "status":
        exists = client.indices.exists(index=index_name)
        print(f"Index '{index_name}' exists: {exists}")
        if exists:
            stats = client.indices.stats(index=index_name)
            docs = stats["indices"][index_name]["total"]["docs"]["count"]
            size_bytes = stats["indices"][index_name]["total"]["store"]["size_in_bytes"]
            print(f"Document count: {docs}")
            print(f"Store size: {size_bytes} bytes")
            aliases = client.indices.get_alias(index=index_name)
            print(f"Active aliases: {list(aliases.get(index_name, {}).get('aliases', {}).keys())}")

    elif args.action == "mapping":
        if client.indices.exists(index=index_name):
            mapping = client.indices.get_mapping(index=index_name)
            print(json.dumps(mapping, indent=2))
        else:
            print(json.dumps(OPENSEARCH_INDEX_MAPPING, indent=2))


if __name__ == "__main__":
    main()
