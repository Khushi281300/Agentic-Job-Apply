"""Webhook triggers - external API to trigger agent actions."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_orchestrator = None


def set_orchestrator(orchestrator: Any) -> None:
    global _orchestrator
    _orchestrator = orchestrator


class TriggerSearchRequest(BaseModel):
    titles: list[str] = Field(default=["Software Engineer"])
    locations: list[str] = Field(default=["Remote"])
    max_results: int = Field(default=20, ge=1, le=100)
    auto_apply: bool = False


class TriggerApplyRequest(BaseModel):
    job_id: str
    force: bool = False


class WebhookCallbackRequest(BaseModel):
    event: str
    source: str
    data: dict[str, Any] = {}


class TriggerResponse(BaseModel):
    status: str = "accepted"
    task_id: Optional[str] = None
    message: str = ""


@router.post("/trigger/search", response_model=TriggerResponse)
async def trigger_search(request: TriggerSearchRequest, background_tasks: BackgroundTasks):
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    background_tasks.add_task(
        _run_search,
        titles=request.titles,
        locations=request.locations,
        auto_apply=request.auto_apply,
    )
    return TriggerResponse(
        status="accepted",
        message=f"Search triggered for {request.titles} in {request.locations}",
    )


@router.post("/trigger/apply", response_model=TriggerResponse)
async def trigger_apply(request: TriggerApplyRequest, background_tasks: BackgroundTasks):
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    background_tasks.add_task(_run_apply, job_id=request.job_id)
    return TriggerResponse(status="accepted", message=f"Apply triggered for job {request.job_id}")


@router.post("/callback")
async def webhook_callback(request: WebhookCallbackRequest):
    logger.info("Webhook callback: %s from %s", request.event, request.source)
    return {"status": "received", "event": request.event}


@router.get("/status")
async def webhook_status():
    return {"status": "running", "orchestrator_ready": _orchestrator is not None}


async def _run_search(titles: list[str], locations: list[str], auto_apply: bool) -> None:
    try:
        if auto_apply:
            await _orchestrator.run()
        else:
            await _orchestrator.run_search_only()
    except Exception as e:
        logger.error("Webhook search failed: %s", e)


async def _run_apply(job_id: str) -> None:
    try:
        application = await _orchestrator.db.get_application(job_id)
        if not application:
            logger.error("Job %s not found in DB", job_id)
            return
        from job_agent_contracts.models import JobListing
        job = JobListing(**application)
        match = await _orchestrator.matcher_agent.run(job=job)
        tailored = await _orchestrator.resume_agent.run(job=job, match=match)
        await _orchestrator.apply_agent.run(job=job, match=match, resume=tailored)
    except Exception as e:
        logger.error("Webhook apply failed: %s", e)
