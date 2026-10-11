"""
OM Search - Ingestion Priority & Fairness Policy Engine
Configurable scheduling profiles (BOOTSTRAP vs STEADY_STATE), queue aging,
source worker budgets, and emergency pause switches.
"""
from dataclasses import dataclass
from typing import Dict, Any


class SchedulingProfile:
    BOOTSTRAP = "BOOTSTRAP"
    STEADY_STATE = "STEADY_STATE"
    CUSTOM = "CUSTOM"


@dataclass
class SourceBudget:
    max_workers: int
    reserved_min_workers: int
    weight: float
    is_paused: bool = False


class IngestionPolicyEngine:
    """
    Governs resource allocation, priority aging, and emergency controls.
    """

    def __init__(self, profile: str = SchedulingProfile.STEADY_STATE):
        self._profile = profile
        self.globally_paused = False
        self.aging_score_per_minute = 0.5

        # Initialize budgets based on profile
        self.budgets: Dict[str, SourceBudget] = {}
        self.set_profile(profile)

    @property
    def profile(self) -> str:
        return self._profile

    def set_profile(self, profile: str) -> None:
        self._profile = profile
        if profile == SchedulingProfile.BOOTSTRAP:
            # Historical archive gets larger share, live crawler retains reserved minimum
            self.budgets["live_crawler"] = SourceBudget(
                max_workers=3,
                reserved_min_workers=1,
                weight=0.3,
            )
            self.budgets["archive_importer"] = SourceBudget(
                max_workers=8,
                reserved_min_workers=2,
                weight=0.7,
            )
        elif profile == SchedulingProfile.STEADY_STATE:
            # Live crawling and freshness gets larger share, archive continues at lower capacity
            self.budgets["live_crawler"] = SourceBudget(
                max_workers=6,
                reserved_min_workers=2,
                weight=0.7,
            )
            self.budgets["archive_importer"] = SourceBudget(
                max_workers=3,
                reserved_min_workers=1,
                weight=0.3,
            )
        else:
            # Balanced custom defaults
            self.budgets["live_crawler"] = SourceBudget(max_workers=4, reserved_min_workers=1, weight=0.5)
            self.budgets["archive_importer"] = SourceBudget(max_workers=4, reserved_min_workers=1, weight=0.5)

    def pause_source(self, source_type: str) -> None:
        if source_type in self.budgets:
            self.budgets[source_type].is_paused = True

    def resume_source(self, source_type: str) -> None:
        if source_type in self.budgets:
            self.budgets[source_type].is_paused = False

    def pause_all(self) -> None:
        self.globally_paused = True

    def resume_all(self) -> None:
        self.globally_paused = False

    def is_source_runnable(self, source_type: str) -> bool:
        if self.globally_paused:
            return False
        budget = self.budgets.get(source_type)
        if not budget:
            return True
        return not budget.is_paused

    def calculate_priority_score(
        self,
        priority_class: str,
        base_priority: int = 0,
        age_minutes: float = 0.0,
    ) -> float:
        """
        Calculates dynamic scheduling score with aging to prevent starvation.
        """
        class_multipliers = {
            "URGENT": 100.0,
            "ROUTINE": 20.0,
            "BULK_ARCHIVE": 10.0,
            "RETRY": 5.0,
        }
        class_base = class_multipliers.get(priority_class, 10.0)
        aging_bonus = age_minutes * self.aging_score_per_minute
        return class_base + float(base_priority) + aging_bonus

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self._profile,
            "globally_paused": self.globally_paused,
            "aging_score_per_minute": self.aging_score_per_minute,
            "budgets": {
                k: {
                    "max_workers": v.max_workers,
                    "reserved_min_workers": v.reserved_min_workers,
                    "weight": v.weight,
                    "is_paused": v.is_paused,
                }
                for k, v in self.budgets.items()
            },
        }
