"""Profile strength scoring — analyzes resume against market demand.

Evaluates how well the user's profile aligns with in-demand skills
and suggests improvements based on job market data.

Usage:
    scorer = ProfileStrengthScorer(db=db, llm=llm)
    report = await scorer.analyze()
"""

import logging
from collections import Counter
from typing import Any

from job_agent_contracts.interfaces import LLMProvider
from job_agent_services.stores.sqlite import Database

logger = logging.getLogger(__name__)


class ProfileStrengthReport:
    """Structured report of profile strengths and weaknesses."""

    def __init__(self, overall_score: float, strengths: list[str],
                 gaps: list[str], recommendations: list[str],
                 market_demand: dict[str, int], sample_size: int):
        self.overall_score = overall_score
        self.strengths = strengths
        self.gaps = gaps
        self.recommendations = recommendations
        self.market_demand = market_demand
        self.sample_size = sample_size

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "strengths": self.strengths,
            "gaps": self.gaps,
            "recommendations": self.recommendations,
            "market_demand_top_skills": dict(
                sorted(self.market_demand.items(), key=lambda x: x[1], reverse=True)[:15]
            ),
            "sample_size": self.sample_size,
        }


class ProfileStrengthScorer:
    """Analyzes user profile against actual job market data from searches.

    Strategy:
    1. Extract skills mentioned in recent job descriptions
    2. Compare with user's profile skills
    3. Score coverage and identify gaps
    4. Use LLM to generate actionable recommendations
    """

    def __init__(self, db: Database, llm: LLMProvider):
        self._db = db
        self._llm = llm

    async def analyze(self, user_skills: list[str] | None = None) -> ProfileStrengthReport:
        """Run full profile analysis against market data.

        Args:
            user_skills: Explicit skill list. If None, extracted from match_data.
        """
        all_jobs = await self._db.get_all_jobs_detailed()

        if not all_jobs:
            return ProfileStrengthReport(
                overall_score=0.5,
                strengths=[],
                gaps=["No job data available for analysis"],
                recommendations=["Run a pipeline search to gather market data"],
                market_demand={},
                sample_size=0,
            )

        # Extract market demand from job data
        market_skills = self._extract_market_skills(all_jobs)

        # Get user skills from match data if not provided
        if user_skills is None:
            user_skills = self._extract_user_skills(all_jobs)

        # Calculate coverage
        user_skills_lower = {s.lower() for s in user_skills}
        top_demand = [skill for skill, _ in market_skills.most_common(20)]

        matched = [s for s in top_demand if s.lower() in user_skills_lower]
        missing = [s for s in top_demand if s.lower() not in user_skills_lower]

        coverage = len(matched) / max(len(top_demand), 1)

        # Generate AI recommendations
        recommendations = await self._generate_recommendations(
            matched, missing, market_skills
        )

        return ProfileStrengthReport(
            overall_score=coverage,
            strengths=matched[:10],
            gaps=missing[:10],
            recommendations=recommendations,
            market_demand=dict(market_skills.most_common(15)),
            sample_size=len(all_jobs),
        )

    def _extract_market_skills(self, jobs: list[dict]) -> Counter:
        """Count skill frequency across all job descriptions."""
        import json
        skill_counter: Counter = Counter()

        for job in jobs:
            match_data = job.get("match_data", "{}")
            try:
                data = json.loads(match_data) if match_data else {}
            except (json.JSONDecodeError, TypeError):
                continue

            # Extract from matched and missing skills
            for skill in data.get("matched_skills", []):
                skill_counter[skill.lower()] += 1
            for skill in data.get("missing_skills", []):
                skill_counter[skill.lower()] += 1

        return skill_counter

    def _extract_user_skills(self, jobs: list[dict]) -> list[str]:
        """Extract user's skills from match data (skills that were matched)."""
        import json
        skills: set[str] = set()

        for job in jobs:
            match_data = job.get("match_data", "{}")
            try:
                data = json.loads(match_data) if match_data else {}
            except (json.JSONDecodeError, TypeError):
                continue
            for skill in data.get("matched_skills", []):
                skills.add(skill)

        return list(skills)

    async def _generate_recommendations(
        self, matched: list[str], missing: list[str], market: Counter
    ) -> list[str]:
        """Use LLM to generate actionable improvement recommendations."""
        if not missing:
            return ["Your profile covers the top in-demand skills well!"]

        prompt = (
            f"Based on job market data, a candidate has these strengths: {', '.join(matched[:8])}.\n"
            f"They are missing these in-demand skills: {', '.join(missing[:8])}.\n\n"
            f"Give exactly 3 concise, actionable recommendations to improve their profile. "
            f"Focus on the highest-impact skills to learn. One sentence each."
        )

        try:
            response = await self._llm.generate(
                prompt,
                system="You are a career coach. Be specific and actionable.",
                temperature=0.5,
            )
            # Split into individual recommendations
            lines = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.strip().split("\n")
                if line.strip() and len(line.strip()) > 10
            ]
            return lines[:5] if lines else [f"Focus on learning: {', '.join(missing[:3])}"]
        except Exception as e:
            logger.warning("LLM recommendation generation failed: %s", e)
            return [f"Focus on learning: {', '.join(missing[:3])}"]
