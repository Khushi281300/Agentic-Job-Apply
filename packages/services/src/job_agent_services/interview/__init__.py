"""Interview Prep Generator — auto-generates likely interview questions for applied jobs.

Uses the job description, match analysis, and RAG context to generate
role-specific technical and behavioral questions with suggested answers.
"""

import logging
from typing import Any

from job_agent_contracts.interfaces import LLMProvider
from job_agent_services.stores.rag import RAGService

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert technical interview coach. Given a job description and candidate profile, "
    "generate likely interview questions with concise suggested answers. "
    "Return JSON with keys: 'technical' (list of {question, answer}), "
    "'behavioral' (list of {question, answer}), 'company_specific' (list of {question, answer})."
)


class InterviewPrepGenerator:
    """Generates interview prep questions for a job application."""

    def __init__(self, llm: LLMProvider, rag: RAGService | None = None):
        self._llm = llm
        self._rag = rag

    async def generate(
        self,
        job_title: str,
        company: str,
        description: str,
        matched_skills: list[str] | None = None,
        missing_skills: list[str] | None = None,
        user_summary: str = "",
    ) -> dict[str, Any]:
        """Generate interview prep questions and answers.

        Returns:
            {
                "technical": [{"question": str, "answer": str}, ...],
                "behavioral": [{"question": str, "answer": str}, ...],
                "company_specific": [{"question": str, "answer": str}, ...],
            }
        """
        # Get RAG context if available
        rag_context = ""
        if self._rag:
            try:
                rag_context = await self._rag.get_relevant_context(
                    f"interview questions {job_title} {company}"
                )
            except Exception:
                pass

        prompt = self._build_prompt(
            job_title, company, description,
            matched_skills or [], missing_skills or [],
            user_summary, rag_context,
        )

        try:
            result = await self._llm.generate_json(prompt, system=_SYSTEM_PROMPT)
            # Ensure expected structure
            return {
                "technical": result.get("technical", [])[:8],
                "behavioral": result.get("behavioral", [])[:5],
                "company_specific": result.get("company_specific", [])[:3],
                "job_title": job_title,
                "company": company,
            }
        except Exception as e:
            logger.error("Interview prep generation failed: %s", e)
            return {
                "technical": [],
                "behavioral": [],
                "company_specific": [],
                "error": str(e),
            }

    def _build_prompt(
        self, title: str, company: str, description: str,
        matched: list[str], missing: list[str],
        user_summary: str, rag_context: str,
    ) -> str:
        sections = [
            f"## Job: {title} at {company}",
            f"### Description:\n{description[:3000]}",
        ]
        if matched:
            sections.append(f"### Candidate's matched skills: {', '.join(matched)}")
        if missing:
            sections.append(f"### Skills to prepare for (gaps): {', '.join(missing)}")
        if user_summary:
            sections.append(f"### Candidate background: {user_summary[:500]}")
        if rag_context:
            sections.append(f"### Context from past applications:\n{rag_context[:1000]}")

        sections.append(
            "\nGenerate 5-8 technical questions (with answers), "
            "3-5 behavioral questions (with STAR-method answers), "
            "and 2-3 company-specific questions. "
            "Focus on the skills gaps and role-specific scenarios."
        )
        return "\n\n".join(sections)
