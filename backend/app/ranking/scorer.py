from typing import Dict, Any, List, Tuple
from app.ranking.config import RankingConfig, DEFAULT_RANKING_CONFIG
from app.ranking.features import CandidateFeatures


class RerankingScorer:
    """
    Computes final ranking scores from extracted feature vectors using versioned configuration weights.
    """

    def __init__(self, config: RankingConfig = DEFAULT_RANKING_CONFIG):
        self.config = config

    def score_candidate(self, features: CandidateFeatures) -> Tuple[float, List[str]]:
        explanations: List[str] = []

        # 1. Lexical BM25 component
        bm25_part = self.config.weight_bm25 * features.bm25_norm
        if features.bm25_norm >= 0.7:
            explanations.append("Strong lexical BM25 relevance")

        # 2. Title and phrase match component
        title_signal = (features.title_coverage * 0.6) + (features.exact_title_match * 0.4)
        if self.config.enable_phrase_boost and features.phrase_match > 0:
            title_signal = min(1.0, title_signal + (0.3 * features.phrase_match))
            explanations.append("Matched quoted or exact phrase")

        if features.exact_title_match > 0:
            explanations.append("Exact title match")

        title_part = self.config.weight_title_coverage * title_signal

        # 3. Link Authority component
        if self.config.enable_authority:
            auth_part = self.config.weight_authority * features.authority
            if features.authority > 0.3:
                explanations.append("High link graph authority (PageRank)")
        else:
            auth_part = 0.0

        # 4. Freshness component
        if self.config.enable_freshness:
            fresh_part = self.config.weight_freshness * features.freshness
            if features.freshness > 0.4:
                explanations.append("Recent publication date boost")
        else:
            fresh_part = 0.0

        # 5. Quality component
        if self.config.enable_quality_filter:
            qual_part = self.config.weight_quality * features.quality
        else:
            qual_part = 0.0

        # Sum linear combination
        total_score = bm25_part + title_part + auth_part + fresh_part + qual_part

        # 5b. Search Keyword Accuracy Boost (ensures exact keywords in search box rank top)
        if features.keyword_coverage >= 1.0:
            total_score += 0.35
            explanations.append("Matches 100% of search keywords")
        elif features.keyword_coverage >= 0.5:
            total_score += 0.15 * features.keyword_coverage
        else:
            total_score *= 0.40
            explanations.append("Penalized: missing search keywords")

        if features.exact_title_match > 0:
            total_score += 0.25

        # 6. Anti-spam penalty
        if features.spam_risk > 0.4:
            total_score *= self.config.spam_penalty_multiplier
            explanations.append("Penalized for keyword stuffing / high spam risk")

        return round(total_score, 4), explanations
