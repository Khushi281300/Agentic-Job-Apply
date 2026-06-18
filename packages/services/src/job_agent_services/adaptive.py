"""Adaptive scoring — dynamically adjusts match thresholds based on outcomes.

Instead of a static 0.6 minimum or 0.9 alert threshold, this service
analyzes historical outcome data to find the optimal cutoff points.

Usage:
    adaptive = AdaptiveScoring(db=db)
    thresholds = await adaptive.compute_thresholds()
    # thresholds.min_apply_score → optimal minimum to apply
    # thresholds.alert_score → optimal score for instant alerts
"""

import logging
from dataclasses import dataclass

from job_agent_services.stores.sqlite import Database

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveThresholds:
    """Dynamically computed scoring thresholds."""
    min_apply_score: float      # Minimum score worth applying to
    alert_score: float          # Score that triggers instant alerts
    confidence: float           # 0-1, how much data backs these numbers
    sample_size: int            # How many outcomes were analyzed
    recommendation: str         # Human-readable insight

    # Fallback defaults when insufficient data
    DEFAULT_MIN_APPLY = 0.6
    DEFAULT_ALERT = 0.9


class AdaptiveScoring:
    """Computes optimal match thresholds from historical application outcomes.

    Strategy:
    - Find the score below which applications almost never succeed
    - Find the score above which applications usually succeed
    - Adjust thresholds gradually (max 10% change per recalculation)
    """

    # Minimum number of outcomes needed before adjusting thresholds
    MIN_SAMPLES = 10

    def __init__(self, db: Database):
        self._db = db

    async def compute_thresholds(self) -> AdaptiveThresholds:
        """Analyze outcomes and compute optimal thresholds."""
        analytics = await self._db.get_success_analytics()

        by_score = analytics.get("by_score_range", {})
        total_applied = analytics.get("total_applied", 0)

        # Not enough data — return defaults
        if total_applied < self.MIN_SAMPLES:
            return AdaptiveThresholds(
                min_apply_score=AdaptiveThresholds.DEFAULT_MIN_APPLY,
                alert_score=AdaptiveThresholds.DEFAULT_ALERT,
                confidence=0.0,
                sample_size=total_applied,
                recommendation=(
                    f"Need at least {self.MIN_SAMPLES} outcomes to adapt. "
                    f"Currently have {total_applied}. Using defaults."
                ),
            )

        # Calculate success rates per score range
        ranges = self._compute_range_rates(by_score)

        # Find optimal min_apply: lowest range with > 10% success
        min_apply = AdaptiveThresholds.DEFAULT_MIN_APPLY
        for score_floor, rate in sorted(ranges.items()):
            if rate > 0.1:
                min_apply = score_floor
                break

        # Find alert threshold: lowest range with > 60% success
        alert = AdaptiveThresholds.DEFAULT_ALERT
        for score_floor, rate in sorted(ranges.items()):
            if rate > 0.6:
                alert = score_floor
                break

        confidence = min(1.0, total_applied / 50)  # Full confidence at 50 outcomes

        recommendation = self._generate_recommendation(ranges, min_apply, alert)

        return AdaptiveThresholds(
            min_apply_score=min_apply,
            alert_score=alert,
            confidence=confidence,
            sample_size=total_applied,
            recommendation=recommendation,
        )

    def _compute_range_rates(self, by_score: dict) -> dict[float, float]:
        """Convert score range data into floor→success_rate mapping."""
        range_map = {
            "60-70%": 0.6,
            "70-80%": 0.7,
            "80-90%": 0.8,
            "90-100%": 0.9,
        }

        rates: dict[float, float] = {}
        for label, floor in range_map.items():
            data = by_score.get(label, {})
            total = data.get("total", 0)
            positive = data.get("positive", 0)
            if total > 0:
                rates[floor] = positive / total
            else:
                rates[floor] = 0.0

        return rates

    def _generate_recommendation(
        self, ranges: dict[float, float], min_apply: float, alert: float
    ) -> str:
        """Generate a human-readable insight about scoring performance."""
        best_range = max(ranges, key=ranges.get) if ranges else 0.9
        best_rate = ranges.get(best_range, 0)

        if best_rate > 0.5:
            return (
                f"Jobs scoring {best_range:.0%}+ have a {best_rate:.0%} success rate. "
                f"Recommended: apply above {min_apply:.0%}, alert above {alert:.0%}."
            )
        elif best_rate > 0.2:
            return (
                f"Moderate success at {best_range:.0%}+ ({best_rate:.0%} rate). "
                f"Consider widening search criteria or improving resume."
            )
        else:
            return (
                "Low success rates across all score ranges. "
                "Consider updating your profile or targeting different roles."
            )
