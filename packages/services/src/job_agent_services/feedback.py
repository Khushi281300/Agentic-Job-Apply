"""Feedback loop — indexes application outcomes into RAG for learning.

When an outcome is recorded (offer, interview, rejected, etc.), this service
feeds structured context back into the vector store so the matcher can
learn from real-world results over time.

Usage:
    feedback = FeedbackService(rag=rag, db=db)
    await feedback.process_outcome(job_id="remoteok_123", outcome="interview")
"""

import logging
from typing import Any

from job_agent_services.stores.rag import RAGService
from job_agent_services.stores.sqlite import Database

logger = logging.getLogger(__name__)

# Outcome sentiment for RAG context (higher = better signal)
_OUTCOME_WEIGHTS = {
    "offer": 1.0,
    "interview": 0.8,
    "callback": 0.6,
    "no_response": 0.2,
    "rejected": 0.0,
}


class FeedbackService:
    """Feeds application outcomes back into RAG for continuous learning.

    Indexes structured outcome documents so the matcher can retrieve
    context like "Last time you applied to a similar role at Company X,
    you got an interview" — improving future scoring accuracy.
    """

    def __init__(self, rag: RAGService, db: Database):
        self._rag = rag
        self._db = db

    async def process_outcome(self, job_id: str, outcome: str) -> None:
        """Index an outcome into RAG for future retrieval.

        Creates a searchable document describing what happened,
        including job details and the result.
        """
        # Fetch job details from DB
        all_jobs = await self._db.get_all_jobs_detailed()
        job_data = next((j for j in all_jobs if j["id"] == job_id), None)

        if not job_data:
            logger.warning("Feedback: job %s not found, skipping RAG indexing", job_id)
            return

        # Build structured feedback document
        feedback_text = self._build_feedback_document(job_data, outcome)

        # Index into RAG
        await self._rag.store.add(
            doc_id=f"outcome_{job_id}",
            text=feedback_text,
            metadata={
                "type": "application_outcome",
                "outcome": outcome,
                "company": job_data.get("company", ""),
                "title": job_data.get("title", ""),
                "source": job_data.get("source", ""),
                "match_score": job_data.get("match_score", 0.0),
                "sentiment": _OUTCOME_WEIGHTS.get(outcome, 0.3),
            },
        )

        logger.info(
            "Feedback indexed: %s at %s → %s (score was %.0f%%)",
            job_data.get("title"), job_data.get("company"),
            outcome, (job_data.get("match_score", 0) or 0) * 100,
        )

    def _build_feedback_document(self, job_data: dict[str, Any], outcome: str) -> str:
        """Create a natural-language description of the outcome for RAG retrieval."""
        title = job_data.get("title", "Unknown Role")
        company = job_data.get("company", "Unknown Company")
        source = job_data.get("source", "unknown")
        score = job_data.get("match_score", 0) or 0
        location = job_data.get("location", "Remote")

        outcome_description = {
            "offer": "received a job offer",
            "interview": "was invited to interview",
            "callback": "received a callback/response",
            "rejected": "was rejected",
            "no_response": "received no response",
        }.get(outcome, outcome)

        return (
            f"Application outcome: Applied to '{title}' at {company} "
            f"(location: {location}, source: {source}). "
            f"Match score was {score:.0%}. "
            f"Result: {outcome_description}. "
            f"This data helps calibrate future job matching."
        )

    async def sync_all_outcomes(self) -> int:
        """Batch-index all recorded outcomes that aren't yet in RAG.

        Useful for initial setup or reindexing. Returns count of indexed outcomes.
        """
        all_jobs = await self._db.get_all_jobs_detailed()
        count = 0

        for job in all_jobs:
            # Only index jobs with recorded outcomes
            if not job.get("outcome"):
                continue

            await self.process_outcome(job["id"], job["outcome"])
            count += 1

        logger.info("Feedback sync: indexed %d outcomes into RAG", count)
        return count
