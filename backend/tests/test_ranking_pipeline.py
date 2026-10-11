import pytest
from datetime import datetime, timezone, timedelta

from app.ranking.query_processor import QueryProcessor
from app.ranking.features import FeatureExtractor
from app.ranking.scorer import RerankingScorer
from app.ranking.config import RankingConfig
from app.ranking.freshness import FreshnessScorer
from app.ranking.quality import QualityAnalyzer
from app.ranking.deduplication import NearDuplicateSuppressor
from app.services.search_service import SearchService


def test_feature_extractor_and_scorer():
    qp = QueryProcessor()
    extractor = FeatureExtractor()
    scorer = RerankingScorer()

    query = qp.process('python tutorial')
    candidate = {
        "id": "doc1",
        "url": "https://example.com/python-tutorial",
        "title": "Python Tutorial Guide",
        "content": "Learn python programming language basics and tutorial.",
        "score": 12.5,
    }

    features = extractor.extract(candidate, query)
    assert 0.0 <= features.bm25_norm <= 1.0
    assert features.title_coverage > 0.0

    score, explanations = scorer.score_candidate(features)
    assert score > 0.0
    assert len(explanations) > 0


def test_freshness_scorer_query_intent_gating():
    scorer = FreshnessScorer(half_life_days=30.0)
    now = datetime.now(timezone.utc)
    recent_date = now - timedelta(days=5)
    old_date = now - timedelta(days=365)

    # Freshness-sensitive query
    recent_fresh_score = scorer.compute_score(recent_date, query_intent="freshness", reference_time=now)
    old_fresh_score = scorer.compute_score(old_date, query_intent="freshness", reference_time=now)

    assert recent_fresh_score > old_fresh_score

    # Evergreen / Informational query (attenuates freshness)
    evergreen_score = scorer.compute_score(recent_date, query_intent="informational", reference_time=now)
    assert evergreen_score < recent_fresh_score


def test_quality_analyzer_keyword_stuffing_detection():
    analyzer = QualityAnalyzer()

    # Normal text
    normal_text = "FastAPI is a modern web framework for Python with high performance."
    res_normal = analyzer.analyze("FastAPI Guide", normal_text)
    assert res_normal["spam_risk"] == 0.0
    assert res_normal["quality_score"] > 0.1

    # Stuffed text
    stuffed_text = "cheap loans cheap loans cheap loans cheap loans cheap loans cheap loans cheap loans"
    res_stuffed = analyzer.analyze("Loans", stuffed_text)
    assert res_stuffed["spam_risk"] >= 0.5


def test_near_duplicate_suppression():
    suppressor = NearDuplicateSuppressor(similarity_threshold=0.70)

    doc_a = {
        "id": "orig",
        "title": "Introduction to Python Programming",
        "content": "Python is an easy to learn, powerful programming language with efficient high-level data structures.",
    }
    doc_b = {
        "id": "mirror",
        "title": "Introduction to Python Programming Mirror",
        "content": "Python is an easy to learn, powerful programming language with efficient high-level data structures.",
    }
    doc_c = {
        "id": "unique",
        "title": "PostgreSQL Database Engine",
        "content": "PostgreSQL is an open source object-relational database system with strong reliability.",
    }

    accepted, suppressed = suppressor.filter_candidates([doc_a, doc_b, doc_c])

    assert len(accepted) == 2
    assert accepted[0]["id"] == "orig"
    assert accepted[1]["id"] == "unique"
    assert len(suppressed) == 1
    assert suppressed[0]["id"] == "mirror"
    assert suppressed[0]["duplicate_of"] == "orig"


def test_search_service_two_stage_ranking_and_explanation():
    service = SearchService()
    res = service.search(query="python", explain=True)

    assert res.total >= 1
    assert res.query_intent is not None
    assert res.ranking_version is not None

    top_item = res.results[0]
    assert top_item.score > 0.0
    assert isinstance(top_item.explanation, list)
    assert top_item.features is not None
    assert "bm25_norm" in top_item.features
