import pytest
import math
from app.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    average_precision,
    dcg_at_k,
    ideal_dcg_at_k,
    ndcg_at_k,
    evaluate_query_ranking,
)


def test_precision_at_k():
    retrieved = ["d1", "d2", "d3", "d4"]
    grades = {"d1": 3, "d2": 0, "d3": 2, "d4": 0}

    assert precision_at_k(retrieved, grades, k=1) == 1.0
    assert precision_at_k(retrieved, grades, k=2) == 0.5
    assert precision_at_k(retrieved, grades, k=4) == 0.5
    assert precision_at_k([], grades, k=5) == 0.0
    assert precision_at_k(retrieved, grades, k=0) == 0.0


def test_recall_at_k():
    retrieved = ["d1", "d2", "d3", "d4"]
    # Total relevant docs: d1 (3), d3 (2), d5 (1) -> 3 relevant
    grades = {"d1": 3, "d2": 0, "d3": 2, "d4": 0, "d5": 1}

    assert pytest.approx(recall_at_k(retrieved, grades, k=1), 0.001) == 1.0 / 3.0
    assert pytest.approx(recall_at_k(retrieved, grades, k=2), 0.001) == 1.0 / 3.0
    assert pytest.approx(recall_at_k(retrieved, grades, k=4), 0.001) == 2.0 / 3.0

    # Vacuous recall when no relevant documents exist
    assert recall_at_k(retrieved, {}, k=5) == 1.0


def test_reciprocal_rank():
    grades = {"d1": 0, "d2": 2, "d3": 3}
    assert reciprocal_rank(["d1", "d2", "d3"], grades) == 0.5  # First relevant is at rank 2
    assert reciprocal_rank(["d2", "d1"], grades) == 1.0        # First relevant is at rank 1
    assert reciprocal_rank(["d4", "d5"], grades) == 0.0        # No relevant


def test_average_precision():
    # Retrieved: d1 (rel), d2 (non-rel), d3 (rel), d4 (non-rel)
    # Ranks of relevant docs: 1 and 3.
    # P@1 = 1/1 = 1.0. P@3 = 2/3.
    # Total relevant = 2
    # AP = (1.0 + 2/3) / 2 = 1.6666... / 2 = 0.8333...
    retrieved = ["d1", "d2", "d3", "d4"]
    grades = {"d1": 1, "d2": 0, "d3": 1, "d4": 0}

    ap = average_precision(retrieved, grades, k=4)
    assert pytest.approx(ap, 0.001) == (1.0 + (2.0 / 3.0)) / 2.0


def test_dcg_and_ndcg_at_k():
    retrieved = ["d1", "d2", "d3", "d4"]
    grades = {"d1": 3, "d2": 0, "d3": 2, "d4": 0, "d5": 1}

    # Hand calculation:
    # rank 1: d1 -> (2^3 - 1) / log2(2) = 7 / 1 = 7.0
    # rank 2: d2 -> (2^0 - 1) / log2(3) = 0.0
    # rank 3: d3 -> (2^2 - 1) / log2(4) = 3 / 2 = 1.5
    # rank 4: d4 -> 0.0
    # DCG@4 = 7.0 + 1.5 = 8.5
    dcg = dcg_at_k(retrieved, grades, k=4)
    assert pytest.approx(dcg, 0.001) == 8.5

    # Ideal ranking: grades [3, 2, 1, 0]
    # rank 1: (2^3 - 1) / 1 = 7.0
    # rank 2: (2^2 - 1) / log2(3) = 3 / 1.584962500721156 = 1.89278926...
    # rank 3: (2^1 - 1) / log2(4) = 1 / 2 = 0.5
    # IDCG@4 = 7.0 + 1.89278926... + 0.5 = 9.39278926...
    idcg = ideal_dcg_at_k(grades, k=4)
    expected_idcg = 7.0 + (3.0 / math.log2(3)) + 0.5
    assert pytest.approx(idcg, 0.001) == expected_idcg

    # NDCG@4 = 8.5 / 9.39278926... = 0.9049494...
    ndcg = ndcg_at_k(retrieved, grades, k=4)
    assert pytest.approx(ndcg, 0.001) == 8.5 / expected_idcg

    # Edge cases
    assert ndcg_at_k([], grades, k=5) == 0.0
    assert ndcg_at_k(["nonexistent"], {}, k=5) == 0.0


def test_evaluate_query_ranking():
    retrieved = ["d1", "d2", "d3"]
    grades = {"d1": 2, "d2": 1, "d3": 0}
    res = evaluate_query_ranking(retrieved, grades, k_values=[1, 3])

    assert "mrr" in res
    assert "map" in res
    assert "p@1" in res
    assert "p@3" in res
    assert "r@1" in res
    assert "r@3" in res
    assert "ndcg@1" in res
    assert "ndcg@3" in res
    assert res["mrr"] == 1.0
