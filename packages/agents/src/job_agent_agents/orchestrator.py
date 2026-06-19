"""Orchestrator - coordinates all agents via LangGraph + Event Bus.

Supports two execution modes:
1. Graph mode (default): Uses LangGraph stateful workflow with checkpointing
2. Direct mode: Simple sequential pipeline (fallback)
"""

import asyncio
import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from job_agent_agents.base import BaseAgent
from job_agent_agents.search import JobSearchAgent
from job_agent_agents.matcher import ProfileMatcherAgent
from job_agent_agents.resume import ResumeTailorAgent
from job_agent_agents.apply import ApplicationAgent
from job_agent_contracts.events import EventType
from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.models import (
    ApplicationConfig, JobListing, PipelineResult, SearchConfig, UserProfile,
)
from job_agent_services.stores.sqlite import Database
from job_agent_services.stores.rag import RAGService
from job_agent_services.observability.tracing import tracer

logger = logging.getLogger(__name__)
console = Console()


class Orchestrator(BaseAgent):
    """Pipeline orchestrator coordinating all agents."""

    def __init__(
        self,
        llm: LLMProvider,
        db: Database,
        rag: RAGService | None = None,
        user_profile: UserProfile | None = None,
        search_config: SearchConfig | None = None,
        app_config: ApplicationConfig | None = None,
        job_sources: list | None = None,
        email_applicant=None,
        notifier=None,
    ):
        super().__init__("orchestrator", llm=llm, rag=rag)
        self.db = db
        self.user_profile = user_profile or UserProfile()
        self.search_config = search_config or SearchConfig()
        self.app_config = app_config or ApplicationConfig()

        self.search_agent = JobSearchAgent(
            llm=llm, db=db, rag=rag,
            titles=self.search_config.titles,
            locations=self.search_config.locations,
            extra_sources=job_sources,
        )
        self.matcher_agent = ProfileMatcherAgent(
            llm=llm, db=db, rag=rag,
            user_profile=self.user_profile,
            search_config=self.search_config,
            app_config=self.app_config,
            min_score=self.app_config.min_match_score,
            notifier=notifier,
        )
        self.resume_agent = ResumeTailorAgent(
            llm=llm, rag=rag,
            user_profile=self.user_profile,
        )
        self.apply_agent = ApplicationAgent(
            llm=llm, db=db, rag=rag,
            user_profile=self.user_profile,
            app_config=self.app_config,
            resume_path=self.user_profile.resume_path,
            email_applicant=email_applicant,
        )

    def _capabilities(self) -> list[str]:
        return ["pipeline_orchestration", "agent_coordination", "langgraph_workflow"]

    def _skills(self) -> list[str]:
        return ["run_pipeline", "run_graph", "search_only", "get_stats"]

    async def run(self, **kwargs: Any) -> PipelineResult:
        """Execute pipeline using LangGraph workflow (with tracing)."""
        use_graph = kwargs.get("use_graph", True)
        if use_graph:
            return await self.run_graph(**kwargs)
        return await self.run_direct(**kwargs)

    async def run_graph(self, **kwargs: Any) -> PipelineResult:
        """Execute the LangGraph stateful workflow."""
        from job_agent_agents.workflows.graph import build_graph

        self.logger.info("Starting LangGraph pipeline...")
        await self._emit(EventType.PIPELINE_STARTED, {})

        empty_result = PipelineResult()

        if not await self.llm.is_available():
            console.print("[red]ERROR: Ollama not running or model not found.[/red]")
            return empty_result

        console.print("[green]✓[/green] Ollama connected")
        console.print("[green]✓[/green] LangGraph workflow active")

        if tracer.is_enabled:
            console.print("[green]✓[/green] LangSmith tracing enabled")

        today_count = await self.db.get_today_application_count()
        remaining = self.app_config.max_applications_per_day - today_count
        if remaining <= 0:
            console.print("[yellow]Daily limit reached.[/yellow]")
            return empty_result

        console.print(f"[blue]Remaining today: {remaining}[/blue]")

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from pathlib import Path

        Path("data").mkdir(exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string("data/checkpoints.db") as checkpointer:
            graph = build_graph(
                self.search_agent, self.matcher_agent,
                self.resume_agent, self.apply_agent, self.db,
                checkpointer=checkpointer,
            )

            initial_state: dict = {
                "search_titles": self.search_config.titles,
                "search_locations": self.search_config.locations,
                "min_match_score": self.app_config.min_match_score,
                "auto_submit": kwargs.get("auto_submit", self.app_config.auto_submit),
                "max_applications": remaining,
                "discovered_jobs": [],
                "current_job": None,
                "current_match": None,
                "current_tailored": None,
                "jobs_to_match": [],
                "matched_jobs": [],
                "jobs_to_apply": [],
                "applied_count": 0,
                "failed_count": 0,
                "rejected_count": 0,
                "errors": [],
                "audit_trail": [],
                "should_continue": True,
                "needs_human_review": False,
            }

            async with tracer.aspan("pipeline.langgraph", metadata={"mode": "graph"}):
                config = {"configurable": {"thread_id": "pipeline-run"}}
                result = await graph.ainvoke(initial_state, config=config)

        stats = PipelineResult(
            searched=len(result.get("discovered_jobs", [])),
            matched=len(result.get("matched_jobs", [])),
            applied=result.get("applied_count", 0),
            failed=result.get("failed_count", 0),
            emailed=result.get("emailed_count", 0),
            errors=result.get("errors", []),
        )

        await self._emit(EventType.PIPELINE_COMPLETED, stats.model_dump())
        self._print_summary(stats)
        return stats

    async def run_direct(self, **kwargs: Any) -> PipelineResult:
        """Fallback: Execute pipeline directly without LangGraph."""
        self.logger.info("Starting direct pipeline...")
        stats = PipelineResult()

        await self._emit(EventType.PIPELINE_STARTED, {})

        if not await self.llm.is_available():
            console.print("[red]ERROR: Ollama not running or model not found.[/red]")
            return stats

        console.print("[green]✓[/green] Ollama connected (direct mode)")

        today_count = await self.db.get_today_application_count()
        remaining = self.app_config.max_applications_per_day - today_count
        if remaining <= 0:
            console.print("[yellow]Daily limit reached.[/yellow]")
            return stats

        # Step 1: Search
        async with tracer.aspan("pipeline.search"):
            console.print("\n[bold]Searching...[/bold]")
            new_jobs = await self.search_agent.run()
            stats.searched = len(new_jobs)
            console.print(f"Found {len(new_jobs)} new listings")

        if not new_jobs:
            return stats

        # Step 2: Fetch details + Match (parallel)
        async with tracer.aspan("pipeline.match"):
            console.print("\n[bold]Analyzing matches...[/bold]")
            matched_jobs: list[tuple[JobListing, Any]] = []

            async def _fetch_and_match(job: JobListing):
                job = await self.search_agent.fetch_job_details(job)
                if not job.description:
                    return None
                match = await self.matcher_agent.run(job=job)
                return (job, match)

            results = await asyncio.gather(
                *(_fetch_and_match(j) for j in new_jobs),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException) or result is None:
                    continue
                job, match = result
                if match.overall_score >= self.app_config.min_match_score:
                    matched_jobs.append((job, match))
                    console.print(f"  [green]✓[/green] {job.title} @ {job.company} ({match.overall_score:.0%})")
                else:
                    console.print(f"  [dim]✗ {job.title} @ {job.company} ({match.overall_score:.0%})[/dim]")

        stats.matched = len(matched_jobs)
        if not matched_jobs:
            return stats

        # Step 3: Tailor + Apply (parallel)
        async with tracer.aspan("pipeline.apply"):
            console.print("\n[bold]Applying...[/bold]")
            matched_jobs.sort(key=lambda x: x[1].overall_score, reverse=True)

            async def _tailor_and_apply(job, match):
                tailored = await self.resume_agent.run(job=job, match=match)
                success = await self.apply_agent.run(job=job, match=match, resume=tailored)
                return (job, success)

            results = await asyncio.gather(
                *(_tailor_and_apply(job, match) for job, match in matched_jobs[:remaining]),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    stats.failed += 1
                    self.logger.error("Apply error: %s", result)
                    continue
                job, success = result
                if success:
                    stats.applied += 1
                    console.print(f"  [green]✓[/green] Applied: {job.title} @ {job.company}")
                else:
                    stats.failed += 1
                    console.print(f"  [red]✗[/red] Failed: {job.title} @ {job.company}")

        await self._emit(EventType.PIPELINE_COMPLETED, stats.model_dump())
        self._print_summary(stats)
        return stats

    async def run_search_only(self) -> list[JobListing]:
        """Search and match only - no applications."""
        if not await self.llm.is_available():
            console.print("[red]Ollama not available[/red]")
            return []

        async with tracer.aspan("pipeline.search_only"):
            jobs = await self.search_agent.run()

            async def _fetch_match(job):
                job = await self.search_agent.fetch_job_details(job)
                if not job.description:
                    return None
                match = await self.matcher_agent.run(job=job)
                if match.overall_score >= self.app_config.min_match_score:
                    return job
                return None

            results = await asyncio.gather(
                *(_fetch_match(j) for j in jobs),
                return_exceptions=True,
            )
            matched = [r for r in results if r is not None and not isinstance(r, BaseException)]
        return matched

    def _print_summary(self, stats: PipelineResult) -> None:
        table = Table(title="Pipeline Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        table.add_row("Discovered", str(stats.searched))
        table.add_row("Matched", str(stats.matched))
        table.add_row("Applied", str(stats.applied))
        table.add_row("Emailed", str(stats.emailed))
        table.add_row("Failed", str(stats.failed))
        console.print(table)

        trace_stats = tracer.get_stats()
        if trace_stats["total_spans"] > 0:
            console.print(f"[dim]Tracing: {trace_stats['total_spans']} spans recorded[/dim]")
