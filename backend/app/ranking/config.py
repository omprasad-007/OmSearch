from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class RankingConfig:
    """
    Versioned configuration controlling candidate retrieval and two-stage reranking.
    """
    version: str = "3.0.0"

    # Stage 1: Retrieval bounds & field weights
    candidate_pool_size: int = 50
    bm25_title_boost: float = 3.0
    bm25_content_boost: float = 1.0
    bm25_snippet_boost: float = 1.5
    phrase_match_boost: float = 2.0
    exact_title_boost: float = 3.5

    # Stage 2: Reranking signal weights
    weight_bm25: float = 0.55
    weight_title_coverage: float = 0.15
    weight_authority: float = 0.10
    weight_freshness: float = 0.10
    weight_quality: float = 0.10

    # Feature toggles
    enable_phrase_boost: bool = True
    enable_synonyms: bool = True
    enable_authority: bool = True
    enable_freshness: bool = True
    enable_quality_filter: bool = True
    enable_near_dedup: bool = True
    enable_semantic_hybrid: bool = False

    # Freshness half-life in days
    freshness_half_life_days: float = 30.0

    # Minimum quality score required to pass soft filter
    min_quality_score: float = 0.20
    spam_penalty_multiplier: float = 0.50

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RankingConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Default active configuration instance
DEFAULT_RANKING_CONFIG = RankingConfig()
