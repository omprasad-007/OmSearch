import json
from pathlib import Path
from typing import List, Dict, Any
from app.ingestion.normalizer import normalize_url


class SeedLoader:
    @staticmethod
    def load_from_json(file_path: str | Path) -> List[Dict[str, Any]]:
        """Load and validate seed documents or URLs from a JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Seed file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Seed file must contain a JSON list of document objects")

        validated = []
        for item in data:
            if "url" in item:
                item["canonical_url"] = normalize_url(item["url"])
                validated.append(item)
        return validated
