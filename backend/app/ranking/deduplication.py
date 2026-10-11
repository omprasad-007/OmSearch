import re
from typing import List, Set, Dict, Any, Tuple


def compute_shingles(text: str, shingle_size: int = 3) -> Set[str]:
    """
    Generate word n-gram shingles for near-duplicate detection.
    """
    words = [w.lower() for w in re.findall(r"\b\w+\b", text) if w]
    if len(words) < shingle_size:
        return set(words)
    shingles = set()
    for i in range(len(words) - shingle_size + 1):
        shingles.add(" ".join(words[i:i + shingle_size]))
    return shingles


def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return intersection / union if union > 0 else 0.0


class NearDuplicateSuppressor:
    """
    Suppresses near-duplicate candidate documents during search result assembly.
    Retains the higher-ranking representative while preserving alternative URLs.
    """

    def __init__(self, similarity_threshold: float = 0.75, shingle_size: int = 3):
        self.similarity_threshold = similarity_threshold
        self.shingle_size = shingle_size

    def filter_candidates(
        self,
        ranked_candidates: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Takes candidates sorted in descending order of ranking score.
        Returns:
            (unique_candidates, suppressed_duplicates)
        """
        accepted: List[Dict[str, Any]] = []
        suppressed: List[Dict[str, Any]] = []
        accepted_shingles: List[Tuple[Dict[str, Any], Set[str]]] = []

        for candidate in ranked_candidates:
            text = (candidate.get("title", "") + " " + candidate.get("content", "")).strip()
            shingles = compute_shingles(text, shingle_size=self.shingle_size)

            is_dup = False
            for accepted_doc, acc_shingles in accepted_shingles:
                sim = jaccard_similarity(shingles, acc_shingles)
                if sim >= self.similarity_threshold:
                    # Near duplicate detected
                    is_dup = True
                    candidate["duplicate_of"] = accepted_doc.get("id") or accepted_doc.get("url")
                    candidate["jaccard_similarity"] = round(sim, 3)
                    suppressed.append(candidate)
                    break

            if not is_dup:
                accepted.append(candidate)
                accepted_shingles.append((candidate, shingles))

        return accepted, suppressed
