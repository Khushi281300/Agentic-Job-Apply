"""Profile Matcher Agent - scores job listings using AI + RAG context."""

import logging
from typing import Any

from job_agent_agents.base import BaseAgent
from job_agent_agents.llm_utils import SafeLLMCaller
from job_agent_contracts.events import EventType
from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.models import (
    ApplicationConfig, JobListing, JobStatus, MatchLLMResponse, MatchResult,
    SearchConfig, UserProfile,
)
from job_agent_agents.prompts import render
from job_agent_services.stores.sqlite import Database
from job_agent_services.stores.rag import RAGService

logger = logging.getLogger(__name__)


class ProfileMatcherAgent(BaseAgent):
    """Evaluates job-profile fit using AI with RAG-augmented context."""

    HIGH_MATCH_THRESHOLD = 0.9  # Trigger instant alert at 90%+

    def __init__(self, llm: LLMProvider, db: Database, rag: RAGService | None = None,
                 user_profile: UserProfile | None = None, search_config: SearchConfig | None = None,
                 app_config: ApplicationConfig | None = None,
                 min_score: float = 0.6, notifier=None):
        super().__init__("profile_matcher", llm=llm, rag=rag)
        self.db = db
        self.user = user_profile or UserProfile()
        self.search = search_config
        self.min_score = min_score
        self._app_config = app_config or ApplicationConfig(min_match_score=min_score)
        self._notifier = notifier
        self._llm_caller = SafeLLMCaller(llm, self.logger)

    def _capabilities(self) -> list[str]:
        return ["profile_matching", "skill_analysis", "fit_scoring"]

    def _skills(self) -> list[str]:
        return ["score_job_match", "analyze_skills_gap"]

    async def run(self, job: JobListing = None, **kwargs: Any) -> MatchResult:
        """Score a job listing against user profile."""
        if job is None:
            job = kwargs.get("job")
        if not job:
            raise ValueError("Job listing required")

        self.logger.info("Matching: %s at %s", job.title, job.company)
        await self.db.update_status(job.id, JobStatus.ANALYZING)

        # Get RAG context from past similar applications
        rag_context = await self._get_rag_context(
            f"{job.title} {job.company} {' '.join(job.requirements[:5])}"
        )

        # Render prompt from template
        prompt = render(
            "match_job.j2",
            user=self.user.model_dump(),
            search=self.search.model_dump() if self.search else {},
            job=job,
            rag_context=rag_context,
        )

        # Validated LLM call via reusable SafeLLMCaller
        llm_result = await self._llm_caller.validated(
            prompt,
            MatchLLMResponse,
            system="You are a job matching expert. Score dimensions 0.0-1.0. Be realistic and critical.",
            context_label=job.id,
        )
        if llm_result is None:
            await self.db.update_status(job.id, JobStatus.FAILED, error="LLM validation failed")
            return MatchResult(job_id=job.id, overall_score=0.0, reasoning="LLM error")

        match = MatchResult(
            job_id=job.id,
            overall_score=llm_result.overall_score,
            skill_match=llm_result.skill_match,
            experience_match=llm_result.experience_match,
            location_match=llm_result.location_match,
            salary_match=llm_result.salary_match,
            reasoning=llm_result.reasoning,
            matched_skills=llm_result.matched_skills,
            missing_skills=llm_result.missing_skills,
        )

        # Update DB based on score
        if match.overall_score >= self.min_score:
            await self.db.update_match(job.id, match)
            await self._emit(EventType.JOB_MATCHED, {
                "job_id": job.id, "score": match.overall_score
            })
            # High-match instant alert
            if match.overall_score >= self.HIGH_MATCH_THRESHOLD and self._notifier:
                try:
                    await self._notifier.notify(
                        f"🔥 High Match: {match.overall_score:.0%}",
                        f"{job.title} at {job.company}\n"
                        f"Skills: {', '.join(match.matched_skills[:5])}\n"
                        f"URL: {job.url}",
                        level="success",
                    )
                except Exception as e:
                    self.logger.debug("Alert notification failed: %s", e)
        else:
            await self.db.update_status(job.id, JobStatus.REJECTED)
            await self._emit(EventType.JOB_REJECTED, {
                "job_id": job.id, "score": match.overall_score
            })

        self.log_action("match_job", input_data={"job_id": job.id}, output_data={"score": match.overall_score})
        return match
