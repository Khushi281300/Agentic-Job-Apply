"""Resume Tailoring Agent - customizes resume and cover letter with RAG context."""

import logging
from pathlib import Path
from typing import Any

from job_agent_agents.base import BaseAgent
from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.models import JobListing, MatchResult, TailoredResume, UserProfile
from job_agent_agents.prompts import render
from job_agent_services.stores.rag import RAGService

logger = logging.getLogger(__name__)


class ResumeTailorAgent(BaseAgent):
    """Generates tailored resume summaries and cover letters using AI + RAG."""

    def __init__(self, llm: LLMProvider, rag: RAGService | None = None,
                 user_profile: UserProfile | None = None, output_dir: str = "data/cover_letters"):
        super().__init__("resume_tailor", llm=llm, rag=rag)
        self.user = user_profile or UserProfile()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _capabilities(self) -> list[str]:
        return ["resume_tailoring", "cover_letter_generation", "content_personalization"]

    def _skills(self) -> list[str]:
        return ["generate_summary", "write_cover_letter", "highlight_skills"]

    async def run(self, job: JobListing = None, match: MatchResult = None, **kwargs: Any) -> TailoredResume:
        """Generate tailored materials for a job application."""
        job = job or kwargs.get("job")
        match = match or kwargs.get("match")
        if not job or not match:
            raise ValueError("Job and match result required")

        self.logger.info("Tailoring for: %s at %s", job.title, job.company)

        rag_context = await self._get_rag_context(
            f"cover letter {job.title} {job.company} {' '.join(match.matched_skills[:5])}"
        )

        summary = await self._generate_summary(job, match, rag_context)
        cover_letter = await self._generate_cover_letter(job, match, rag_context)

        result = TailoredResume(
            job_id=job.id,
            summary=summary,
            highlighted_skills=match.matched_skills,
            cover_letter=cover_letter,
        )

        self._save_cover_letter(job, cover_letter)

        if self.rag:
            await self.rag.store.add(
                doc_id=f"cover_{job.id}",
                text=f"Cover letter for {job.title} at {job.company}:\n{cover_letter[:500]}",
                metadata={"type": "cover_letter", "company": job.company},
            )

        self.log_action("tailor_resume", input_data={"job_id": job.id})
        return result

    async def _generate_summary(self, job: JobListing, match: MatchResult, rag_context: str) -> str:
        prompt = render("tailor_summary.j2",
                        user=self.user.model_dump(), job=job,
                        matched_skills=match.matched_skills,
                        rag_context=rag_context)
        return await self.llm.generate(
            prompt, system="You are an expert resume writer. Write concise, impactful summaries."
        )

    async def _generate_cover_letter(self, job: JobListing, match: MatchResult, rag_context: str) -> str:
        prompt = render("cover_letter.j2",
                        user=self.user.model_dump(), job=job,
                        matched_skills=match.matched_skills,
                        missing_skills=match.missing_skills,
                        rag_context=rag_context)
        return await self.llm.generate(
            prompt, system="You are an expert cover letter writer. Write compelling, personalized letters."
        )

    def _save_cover_letter(self, job: JobListing, cover_letter: str) -> None:
        safe_name = f"{job.company}_{job.title}".replace(" ", "_").replace("/", "_")[:50]
        file_path = self.output_dir / f"{safe_name}.txt"
        file_path.write_text(cover_letter, encoding="utf-8")
        self.logger.info("Saved: %s", file_path)
