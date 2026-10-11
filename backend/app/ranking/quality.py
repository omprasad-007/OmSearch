import re
from typing import Dict, Any, Tuple


class QualityAnalyzer:
    """
    Computes explainable content quality and search spam risk signals.
    """

    def __init__(self, min_word_count: int = 8, max_term_frequency_ratio: float = 0.18):
        self.min_word_count = min_word_count
        self.max_term_frequency_ratio = max_term_frequency_ratio

    def analyze(self, title: str, content: str) -> Dict[str, float]:
        """
        Analyze document body and title to compute quality_score [0..1] and spam_risk [0..1].
        """
        words = re.findall(r"\b\w+\b", content.lower())
        word_count = len(words)

        if word_count == 0:
            return {"quality_score": 0.0, "spam_risk": 0.8}

        # 1. Length-based quality (smooth ramp reaching 1.0 at ~60 words)
        length_quality = min(1.0, word_count / 60.0)

        # 2. Term repetition / Keyword stuffing
        freq: Dict[str, int] = {}
        for w in words:
            if len(w) > 3:  # ignore short stopwords
                freq[w] = freq.get(w, 0) + 1

        max_freq = max(freq.values()) if freq else 0
        repetition_ratio = max_freq / max(1, word_count)

        is_keyword_stuffed = repetition_ratio > self.max_term_frequency_ratio

        # 3. Title-to-content repetition
        title_words = set(re.findall(r"\b\w+\b", title.lower()))
        title_overlap = sum(1 for tw in title_words if tw in freq and freq[tw] > 10)
        is_repetitive_title = title_overlap > 2 and word_count < 100

        # Calculate spam risk score [0..1]
        spam_risk = 0.0
        if is_keyword_stuffed:
            spam_risk += 0.5
        if is_repetitive_title:
            spam_risk += 0.3
        spam_risk = min(1.0, spam_risk)

        # Combined quality score: length quality penalized if below min_word_count and reduced by spam risk
        if word_count < self.min_word_count:
            length_quality *= (word_count / self.min_word_count)

        quality_score = max(0.05, length_quality * (1.0 - (spam_risk * 0.8)))

        return {
            "quality_score": round(quality_score, 4),
            "spam_risk": round(spam_risk, 4),
            "word_count": float(word_count),
        }
