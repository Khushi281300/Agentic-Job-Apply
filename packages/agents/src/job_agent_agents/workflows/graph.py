"""LangGraph workflow - defines the agent pipeline as a stateful graph."""

import asyncio
import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt

from job_agent_contracts.audit import AuditEntry
from job_agent_contracts.models import (
    JobListing, JobMatchBundle, MatchResult, TailoredResume, ReviewItem,
)
from job_agent_contracts.retry import RETRY_LLM, RETRY_BROWSER, RetryConfig
from job_agent_agents.workflows.nodes import create_agent_node

logger = logging.getLogger(__name__)


# ─── Graph State ─────────────────────────────────────────────────────────────

class JobApplicationState(TypedDict):
    """State that flows through the LangGraph pipeline."""
    # Input
    search_titles: list[str]
    search_locations: list[str]
    min_match_score: float
    auto_submit: bool
    max_applications: int

    # Pipeline state
    discovered_jobs: Annotated[list[JobListing], operator.add]
    current_job: JobListing | None
    current_match: MatchResult | None
    current_tailored: TailoredResume | None

    # Queues
    jobs_to_match: list[JobListing]
    matched_jobs: Annotated[list[JobMatchBundle], operator.add]
    jobs_to_apply: list[JobMatchBundle]

    # Results
    applied_count: int
    failed_count: int
    emailed_count: int
    rejected_count: int
    errors: Annotated[list[str], operator.add]

    # Audit trail
    audit_trail: Annotated[list[AuditEntry], operator.add]

    # Control
    should_continue: bool
    needs_human_review: bool


# ─── Graph Nodes ─────────────────────────────────────────────────────────────

class GraphNodes:
    """Node implementations for the LangGraph workflow."""

    def __init__(self, search_agent, matcher_agent, resume_agent, apply_agent, db):
        self.search_agent = search_agent
        self.matcher_agent = matcher_agent
        self.resume_agent = resume_agent
        self.apply_agent = apply_agent
        self.db = db

    async def search_node(self, state: JobApplicationState) -> dict:
        jobs = await self.search_agent.run()
        return {
            "discovered_jobs": jobs,
            "jobs_to_match": jobs,
            "should_continue": len(jobs) > 0,
        }

    async def fetch_details_node(self, state: JobApplicationState) -> dict:
        jobs_to_match = state.get("jobs_to_match", [])
        results = await asyncio.gather(
            *(self.search_agent.fetch_job_details(job) for job in jobs_to_match),
            return_exceptions=True,
        )
        enriched = [
            r for r in results
            if not isinstance(r, BaseException) and r.description
        ]
        return {"jobs_to_match": enriched}

    async def match_node(self, state: JobApplicationState) -> dict:
        min_score = state.get("min_match_score", 0.6)
        jobs_to_match = state.get("jobs_to_match", [])

        results = await asyncio.gather(
            *(self.matcher_agent.run(job=job) for job in jobs_to_match),
            return_exceptions=True,
        )
        matched: list[JobMatchBundle] = []
        rejected = 0
        for job, result in zip(jobs_to_match, results):
            if isinstance(result, BaseException):
                rejected += 1
                continue
            if result.overall_score >= min_score:
                matched.append(JobMatchBundle(job=job, match=result))
            else:
                rejected += 1

        return {
            "matched_jobs": matched,
            "jobs_to_apply": matched,
            "rejected_count": state.get("rejected_count", 0) + rejected,
            "should_continue": len(matched) > 0,
        }

    async def tailor_node(self, state: JobApplicationState) -> dict:
        jobs_to_apply: list[JobMatchBundle] = state.get("jobs_to_apply", [])

        async def _tailor_one(bundle: JobMatchBundle) -> JobMatchBundle:
            tailored = await self.resume_agent.run(job=bundle.job, match=bundle.match)
            return JobMatchBundle(job=bundle.job, match=bundle.match, tailored=tailored)

        tailored_bundles = await asyncio.gather(
            *(_tailor_one(b) for b in jobs_to_apply),
            return_exceptions=True,
        )
        # Filter out failures
        tailored_bundles = [b for b in tailored_bundles if not isinstance(b, BaseException)]

        return {
            "jobs_to_apply": tailored_bundles,
            "needs_human_review": not state.get("auto_submit", False),
        }

    async def human_review_node(self, state: JobApplicationState) -> dict:
        if state.get("auto_submit", False):
            return {"needs_human_review": False}

        jobs_to_review: list[JobMatchBundle] = state.get("jobs_to_apply", [])
        review_summary = [
            ReviewItem(
                title=bundle.job.title,
                company=bundle.job.company,
                score=bundle.match.overall_score,
                url=bundle.job.url,
            ).model_dump()
            for bundle in jobs_to_review
        ]

        human_decision = interrupt({
            "message": "Please review these applications before submission",
            "jobs": review_summary,
            "instructions": "Resume with {'approved': [indexes], 'rejected': [indexes]}",
        })

        approved_indices = human_decision.get("approved", list(range(len(jobs_to_review))))
        filtered_jobs = [jobs_to_review[i] for i in approved_indices if i < len(jobs_to_review)]

        return {
            "jobs_to_apply": filtered_jobs,
            "needs_human_review": False,
        }

    async def apply_node(self, state: JobApplicationState) -> dict:
        jobs_to_apply: list[JobMatchBundle] = state.get("jobs_to_apply", [])
        max_apps = state.get("max_applications", 10)
        applied = 0
        failed = 0
        errors = []

        for bundle in jobs_to_apply[:max_apps]:
            try:
                success = await self.apply_agent.run(
                    job=bundle.job, match=bundle.match, resume=bundle.tailored,
                )
                if success:
                    applied += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                errors.append(f"{bundle.job.title}: {str(e)}")

        return {
            "applied_count": state.get("applied_count", 0) + applied,
            "failed_count": state.get("failed_count", 0) + failed,
            "errors": errors,
            "should_continue": False,
        }


# ─── Graph Builder ───────────────────────────────────────────────────────────

def build_graph(search_agent, matcher_agent, resume_agent, apply_agent, db, checkpointer=None) -> StateGraph:
    """Build the LangGraph workflow with node factory wrappers."""
    nodes = GraphNodes(search_agent, matcher_agent, resume_agent, apply_agent, db)

    workflow = StateGraph(JobApplicationState)

    workflow.add_node("search", create_agent_node(
        nodes.search_node, "search",
        retry_config=RETRY_LLM,
        output_summary_fn=lambda r: {"job_count": len(r.get("discovered_jobs", []))},
    ))
    workflow.add_node("fetch_details", create_agent_node(
        nodes.fetch_details_node, "fetch_details",
        retry_config=RetryConfig(max_retries=2, base_delay=2.0),
    ))
    workflow.add_node("match", create_agent_node(
        nodes.match_node, "match",
        retry_config=RETRY_LLM,
        skip_if=lambda s: not s.get("jobs_to_match"),
        output_summary_fn=lambda r: {
            "matched": len(r.get("matched_jobs", [])),
            "rejected": r.get("rejected_count", 0),
        },
    ))
    workflow.add_node("tailor", create_agent_node(
        nodes.tailor_node, "tailor",
        retry_config=RETRY_LLM,
        skip_if=lambda s: not s.get("jobs_to_apply"),
    ))
    workflow.add_node("human_review", nodes.human_review_node)
    workflow.add_node("apply", create_agent_node(
        nodes.apply_node, "apply",
        retry_config=RETRY_BROWSER,
        output_summary_fn=lambda r: {
            "applied": r.get("applied_count", 0),
            "failed": r.get("failed_count", 0),
        },
    ))

    # Edges
    workflow.set_entry_point("search")
    workflow.add_edge("search", "fetch_details")
    workflow.add_edge("fetch_details", "match")
    workflow.add_conditional_edges(
        "match",
        _should_continue_to_tailor,
        {"tailor": "tailor", "end": END},
    )
    workflow.add_edge("tailor", "human_review")
    workflow.add_conditional_edges(
        "human_review",
        _should_apply,
        {"apply": "apply", "end": END},
    )
    workflow.add_edge("apply", END)

    return workflow.compile(checkpointer=checkpointer)


def compile_graph_for_display(search_agent, matcher_agent, resume_agent, apply_agent, db):
    """Compile graph WITHOUT checkpointer - for visualization only."""
    nodes = GraphNodes(search_agent, matcher_agent, resume_agent, apply_agent, db)
    workflow = StateGraph(JobApplicationState)

    workflow.add_node("search", create_agent_node(
        nodes.search_node, "search", output_summary_fn=lambda r: {"job_count": len(r.get("discovered_jobs", []))},
    ))
    workflow.add_node("fetch_details", create_agent_node(nodes.fetch_details_node, "fetch_details"))
    workflow.add_node("match", create_agent_node(
        nodes.match_node, "match", skip_if=lambda s: not s.get("jobs_to_match"),
    ))
    workflow.add_node("tailor", create_agent_node(
        nodes.tailor_node, "tailor", skip_if=lambda s: not s.get("jobs_to_apply"),
    ))
    workflow.add_node("human_review", nodes.human_review_node)
    workflow.add_node("apply", create_agent_node(nodes.apply_node, "apply"))

    workflow.set_entry_point("search")
    workflow.add_edge("search", "fetch_details")
    workflow.add_edge("fetch_details", "match")
    workflow.add_conditional_edges("match", _should_continue_to_tailor, {"tailor": "tailor", "end": END})
    workflow.add_edge("tailor", "human_review")
    workflow.add_conditional_edges("human_review", _should_apply, {"apply": "apply", "end": END})
    workflow.add_edge("apply", END)

    return workflow.compile()


def _should_continue_to_tailor(state: JobApplicationState) -> str:
    if state.get("should_continue", False) and state.get("matched_jobs"):
        return "tailor"
    return "end"


def _should_apply(state: JobApplicationState) -> str:
    jobs_to_apply = state.get("jobs_to_apply", [])
    if jobs_to_apply and not state.get("needs_human_review", False):
        return "apply"
    return "end"
