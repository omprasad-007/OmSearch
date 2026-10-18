import math
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.ranking.query_processor import ProcessedQuery
from app.ranking.freshness import FreshnessScorer
from app.ranking.quality import QualityAnalyzer


@dataclass
class CandidateFeatures:
    doc_id: str
    url: str
    bm25_raw: float
    bm25_norm: float
    title_coverage: float
    exact_title_match: float
    phrase_match: float
    keyword_coverage: float
    authority: float
    freshness: float
    quality: float
    spam_risk: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "bm25_raw": round(self.bm25_raw, 3),
            "bm25_norm": round(self.bm25_norm, 3),
            "title_coverage": round(self.title_coverage, 3),
            "exact_title_match": round(self.exact_title_match, 3),
            "phrase_match": round(self.phrase_match, 3),
            "keyword_coverage": round(self.keyword_coverage, 3),
            "authority": round(self.authority, 3),
            "freshness": round(self.freshness, 3),
            "quality": round(self.quality, 3),
            "spam_risk": round(self.spam_risk, 3),
        }


class FeatureExtractor:
    """
    Extracts normalized, bounded feature vectors from candidate documents.
    """

    def __init__(self, freshness_half_life_days: float = 30.0):
        self.freshness_scorer = FreshnessScorer(half_life_days=freshness_half_life_days)
        self.quality_analyzer = QualityAnalyzer()

    def extract(
        self,
        candidate: Dict[str, Any],
        query: ProcessedQuery,
        authority_lookup: Optional[Dict[str, float]] = None,
    ) -> CandidateFeatures:
        doc_id = candidate.get("id") or candidate.get("url", "")
        url = candidate.get("url", "")
        title = candidate.get("title", "")
        content = candidate.get("content", "")
        raw_score = float(candidate.get("_score") or candidate.get("score") or 1.0)

        # 1. Bounded BM25 transform: log(1 + score) normalized assuming typical top BM25 is ~10-30
        bm25_norm = min(1.0, math.log1p(max(0.0, raw_score)) / 3.5)

        # 2. Title term coverage
        title_lower = title.lower()
        title_tokens = set(re.findall(r"\b\w+\b", title_lower))
        if query.tokens:
            overlap = sum(1 for t in query.tokens if t in title_tokens)
            title_coverage = overlap / len(query.tokens)
        else:
            title_coverage = 0.0

        # 3. Exact title match
        exact_title_match = 1.0 if query.normalized_query and query.normalized_query in title_lower else 0.0

        # 4. Phrase match
        phrase_match = 0.0
        if query.quoted_phrases:
            matched_phrases = sum(
                1 for qp in query.quoted_phrases
                if qp.lower() in title_lower or qp.lower() in content.lower()
            )
            phrase_match = matched_phrases / len(query.quoted_phrases)
        elif len(query.tokens) > 1 and query.normalized_query in content.lower():
            phrase_match = 0.5

        # 4b. Specific Keyword Coverage across entire document (title + snippet + content)
        doc_full_text = f"{title} {candidate.get('snippet', '')} {content}".lower()
        if query.tokens:
            matched_kws = sum(1 for t in query.tokens if t in doc_full_text)
            keyword_coverage = matched_kws / len(query.tokens)
        else:
            keyword_coverage = 1.0

        # 5. Link authority (PageRank)
        pr_map = authority_lookup or {}
        raw_pr = pr_map.get(url, 0.0)
        # Log-scaled PageRank normalization
        authority = min(1.0, math.log1p(raw_pr * 100.0) / 2.0) if raw_pr > 0 else 0.05

        # 6. Freshness
        pub_at = candidate.get("published_at")
        if isinstance(pub_at, str):
            try:
                pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
            except Exception:
                pub_at = None

        freshness = self.freshness_scorer.compute_score(
            published_at=pub_at,
            query_intent=query.intent,
        )

        # 7. Quality and Spam
        quality_res = self.quality_analyzer.analyze(title=title, content=content)
        quality = quality_res["quality_score"]
        spam_risk = quality_res["spam_risk"]

        return CandidateFeatures(
            doc_id=doc_id,
            url=url,
            bm25_raw=raw_score,
            bm25_norm=bm25_norm,
            title_coverage=title_coverage,
            exact_title_match=exact_title_match,
            phrase_match=phrase_match,
            keyword_coverage=keyword_coverage,
            authority=authority,
            freshness=freshness,
            quality=quality,
            spam_risk=spam_risk,
        )
