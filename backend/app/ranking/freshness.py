import math
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class FreshnessScorer:
    """
    Computes query-dependent temporal freshness scores using exponential decay.
    """

    def __init__(self, half_life_days: float = 30.0):
        if half_life_days <= 0:
            raise ValueError(f"Half life must be positive, got {half_life_days}")
        self.half_life_days = half_life_days
        # decay_constant lambda = ln(2) / half_life
        self.decay_constant = math.log(2) / self.half_life_days

    def compute_score(
        self,
        published_at: Optional[datetime],
        query_intent: str = "general",
        reference_time: Optional[datetime] = None,
    ) -> float:
        """
        Calculate freshness score in [0.0, 1.0].
        If query is not freshness-sensitive, freshness contribution is sharply attenuated.
        """
        if not published_at:
            # Neutral baseline for documents with unknown publication dates
            return 0.10 if query_intent == "freshness" else 0.05

        ref = reference_time or datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            pub_dt = published_at.replace(tzinfo=timezone.utc)
        else:
            pub_dt = published_at

        # Guard against implausible future timestamps (allow at most 1 day clock skew)
        delta_seconds = (ref - pub_dt).total_seconds()
        if delta_seconds < -86400:
            # Future timestamp -> untrusted, default to neutral
            return 0.05

        age_days = max(0.0, delta_seconds / 86400.0)

        # Exponential decay: score = exp(-lambda * age_days)
        raw_score = math.exp(-self.decay_constant * age_days)

        # Query-intent gating:
        # Full boost for freshness queries; minor tie-breaker for others
        if query_intent == "freshness":
            return round(raw_score, 4)
        else:
            return round(raw_score * 0.15, 4)
