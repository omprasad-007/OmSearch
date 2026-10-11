import math
from typing import List, Dict, Any, Optional


def precision_at_k(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k: int = 10,
    threshold: int = 1,
) -> float:
    """
    Calculate Precision@k: proportion of retrieved documents in top-k that are relevant.
    Relevance is determined if grade >= threshold.
    """
    if k <= 0:
        return 0.0
    cutoff = retrieved_ids[:k]
    if not cutoff:
        return 0.0

    relevant_count = sum(
        1 for doc_id in cutoff
        if relevant_grades.get(doc_id, 0) >= threshold
    )
    return relevant_count / len(cutoff)


def recall_at_k(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k: int = 10,
    threshold: int = 1,
) -> float:
    """
    Calculate Recall@k: proportion of all known relevant documents retrieved in top-k.
    """
    total_relevant = sum(
        1 for grade in relevant_grades.values()
        if grade >= threshold
    )
    if total_relevant == 0:
        return 1.0  # Vacuously complete if no relevant docs exist

    if k <= 0:
        return 0.0

    cutoff = retrieved_ids[:k]
    retrieved_relevant = sum(
        1 for doc_id in cutoff
        if relevant_grades.get(doc_id, 0) >= threshold
    )
    return retrieved_relevant / total_relevant


def reciprocal_rank(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    threshold: int = 1,
) -> float:
    """
    Calculate Reciprocal Rank (RR): 1 / rank of the first relevant document.
    Returns 0.0 if no relevant document is retrieved.
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if relevant_grades.get(doc_id, 0) >= threshold:
            return 1.0 / rank
    return 0.0


def average_precision(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k: int = 10,
    threshold: int = 1,
) -> float:
    """
    Calculate Average Precision (AP@k): mean of precision values calculated at each relevant document rank.
    """
    total_relevant = sum(
        1 for grade in relevant_grades.values()
        if grade >= threshold
    )
    if total_relevant == 0:
        return 0.0

    cutoff = retrieved_ids[:k]
    running_relevant = 0
    precision_sum = 0.0

    for rank, doc_id in enumerate(cutoff, start=1):
        if relevant_grades.get(doc_id, 0) >= threshold:
            running_relevant += 1
            precision_at_rank = running_relevant / rank
            precision_sum += precision_at_rank

    return precision_sum / min(total_relevant, k)


def dcg_at_k(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k: int = 10,
) -> float:
    """
    Calculate Discounted Cumulative Gain (DCG@k) using standard exponential gain:
    DCG_k = sum_{i=1}^k (2^{grade} - 1) / log2(i + 1)
    """
    if k <= 0:
        return 0.0

    dcg = 0.0
    for i, doc_id in enumerate(retrieved_ids[:k], start=1):
        grade = relevant_grades.get(doc_id, 0)
        gain = (2 ** grade) - 1.0
        discount = math.log2(i + 1)
        dcg += gain / discount
    return dcg


def ideal_dcg_at_k(
    relevant_grades: Dict[str, int],
    k: int = 10,
) -> float:
    """
    Calculate Ideal DCG (IDCG@k) by sorting known relevance grades in descending order.
    """
    if k <= 0:
        return 0.0

    sorted_grades = sorted(relevant_grades.values(), reverse=True)
    idcg = 0.0
    for i, grade in enumerate(sorted_grades[:k], start=1):
        gain = (2 ** grade) - 1.0
        discount = math.log2(i + 1)
        idcg += gain / discount
    return idcg


def ndcg_at_k(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k: int = 10,
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (NDCG@k) = DCG@k / IDCG@k.
    Returns 0.0 if IDCG is 0.
    """
    idcg = ideal_dcg_at_k(relevant_grades, k=k)
    if idcg <= 0.0:
        return 0.0
    dcg = dcg_at_k(retrieved_ids, relevant_grades, k=k)
    return min(1.0, max(0.0, dcg / idcg))


def evaluate_query_ranking(
    retrieved_ids: List[str],
    relevant_grades: Dict[str, int],
    k_values: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Comprehensive evaluation of a single query result list across multiple metrics.
    """
    k_vals = k_values or [1, 3, 5, 10]
    metrics = {
        "mrr": reciprocal_rank(retrieved_ids, relevant_grades),
        "map": average_precision(retrieved_ids, relevant_grades, k=max(k_vals)),
    }

    for k in k_vals:
        metrics[f"p@{k}"] = precision_at_k(retrieved_ids, relevant_grades, k=k)
        metrics[f"r@{k}"] = recall_at_k(retrieved_ids, relevant_grades, k=k)
        metrics[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, relevant_grades, k=k)

    return metrics
