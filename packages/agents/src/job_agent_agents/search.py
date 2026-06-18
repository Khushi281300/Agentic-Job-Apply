"""Job Search Agent - discovers jobs using pluggable sources."""

import asyncio
import logging
from typing import Any

from job_agent_agents.base import BaseAgent
from job_agent_contracts.events import EventType
from job_agent_contracts.interfaces import JobSource, LLMProvider
from job_agent_contracts.models import JobListing
from job_agent_agents.prompts import render
from job_agent_services.stores.sqlite import Database
from job_agent_services.stores.rag import RAGService
from job_agent_services.deduplication import JobDeduplicator
from job_agent_services.registry import ServiceRegistry

logger = logging.getLogger(__name__)


class JobSearchAgent(BaseAgent):
    """Discovers jobs from all registered sources and indexes them for RAG."""

    def __init__(self, llm: LLMProvider, db: Database, rag: RAGService | None = None,
                 titles: list[str] | None = None, locations: list[str] | None = None,
                 extra_sources: list[JobSource] | None = None):
        super().__init__("job_search", llm=llm, rag=rag)
        self.db = db
        self.titles = titles or ["Software Engineer"]
        self.locations = locations or ["Remote"]
        self._extra_sources = extra_sources or []

    def _capabilities(self) -> list[str]:
        return ["job_discovery", "web_scraping", "requirement_extraction"]

    def _skills(self) -> list[str]:
        return ["search_jobs", "fetch_details", "extract_requirements"]

    async def run(self, **kwargs: Any) -> list[JobListing]:
        """Search all registered sources for jobs."""
        self.logger.info("Starting job search...")
        all_jobs: list[JobListing] = []

        # Get sources from registry + any extras passed in
        registry = ServiceRegistry()
        sources = registry.list_category("job_source") + self._extra_sources

        if not sources:
            self.logger.warning("No job sources registered!")
            return []

        tasks: list[asyncio.Task] = []
        for source in sources:
            for title in self.titles:
                for location in self.locations:
                    tasks.append(self._search_one(source, title, location))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                self.logger.error("Search task failed: %s", result)
            else:
                all_jobs.extend(result)

        # Deduplicate across sources
        deduplicator = JobDeduplicator()
        all_jobs = deduplicator.deduplicate(all_jobs)

        # Filter already-seen
        new_jobs = []
        for j in all_jobs:
            if not await self.db.is_already_seen(j.url):
                new_jobs.append(j)

        # Save and index
        for job in new_jobs:
            await self.db.save_job(job)
            await self._emit(EventType.JOB_DISCOVERED, {"job_id": job.id, "title": job.title})

        self.log_action("search_complete", output_data={"total": len(all_jobs), "new": len(new_jobs)})
        return new_jobs

    async def _search_one(self, source: JobSource, title: str, location: str) -> list[JobListing]:
        """Search a single source/title/location combination."""
        try:
            return await source.search(title, location)
        except Exception as e:
            self.logger.error("Source %s failed for %s/%s: %s", source.name, title, location, e)
            raise

    async def fetch_job_details(self, job: JobListing) -> JobListing:
        """Fetch full description and extract requirements."""
        registry = ServiceRegistry()
        source = registry.get(f"job_source.{job.source.value}")
        if source:
            description = await source.fetch_details(job.url)
            if description:
                job.description = description
                job.requirements = await self._extract_requirements(description)

                if self.rag:
                    await self.rag.index_job(job.id, job.title, job.company, description)
                    await self._emit(EventType.RAG_INDEXED, {"doc_id": f"job_{job.id}"})

        await self._emit(EventType.JOB_DETAILS_FETCHED, {"job_id": job.id})
        return job

    async def _extract_requirements(self, description: str) -> list[str]:
        prompt = render("extract_requirements.j2", description=description)
        result = await self.llm.generate_json(prompt)
        return result.get("requirements", [])
