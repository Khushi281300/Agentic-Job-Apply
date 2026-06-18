"""FastAPI HTTP server exposing MCP + A2A endpoints."""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from typing import Any

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Rate limiter with periodic cleanup
RATE_LIMIT_MAX = 60  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds


class _RateLimiter:
    """In-memory rate limiter with automatic stale IP cleanup."""

    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        now = time.time()
        bucket = self._buckets[client_ip]
        # Prune expired timestamps in-place
        cutoff = now - RATE_LIMIT_WINDOW
        self._buckets[client_ip] = bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= RATE_LIMIT_MAX:
            return False
        bucket.append(now)
        return True

    def cleanup(self) -> None:
        """Remove stale IPs with no recent requests."""
        now = time.time()
        stale = [ip for ip, times in self._buckets.items()
                 if not times or (now - max(times)) > RATE_LIMIT_WINDOW * 10]
        for ip in stale:
            del self._buckets[ip]


_rate_limiter = _RateLimiter()


async def _verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Validate Bearer token against API_KEY env var. No key = dev mode."""
    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        return
    if credentials is None or credentials.credentials != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def create_api_app(mcp_server, a2a_server, db=None, llm=None) -> FastAPI:
    """Create FastAPI app with MCP and A2A endpoints."""

    app = FastAPI(
        title="Job Apply Agent",
        description="AI-powered job application agent with MCP + A2A protocol support",
        version="0.4.0",
    )

    # ─── CORS ────────────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8501",  # Streamlit dashboard
            "http://localhost:3000",  # Future frontend
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Rate Limiting Middleware ────────────────────────────────────────────

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not _rate_limiter.check(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
        return await call_next(request)

    # ─── Startup / Shutdown ──────────────────────────────────────────────────

    _cleanup_task = None

    @app.on_event("startup")
    async def _startup():
        nonlocal _cleanup_task
        async def _periodic_cleanup():
            while True:
                await asyncio.sleep(600)  # every 10 minutes
                _rate_limiter.cleanup()
        _cleanup_task = asyncio.create_task(_periodic_cleanup())

    @app.on_event("shutdown")
    async def _shutdown():
        if _cleanup_task:
            _cleanup_task.cancel()

    # ─── A2A Endpoints ───────────────────────────────────────────────────────

    @app.get("/.well-known/agent.json")
    async def agent_card():
        return a2a_server.get_agent_card()

    class TaskSendRequest(BaseModel):
        id: str = ""
        message: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

    @app.post("/a2a/tasks/send", dependencies=[Depends(_verify_api_key)])
    async def send_task(request: TaskSendRequest):
        task = await a2a_server.send_task(request.model_dump())
        return task.model_dump()

    @app.get("/a2a/tasks/{task_id}", dependencies=[Depends(_verify_api_key)])
    async def get_task(task_id: str):
        task = await a2a_server.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task.model_dump()

    @app.post("/a2a/tasks/{task_id}/cancel", dependencies=[Depends(_verify_api_key)])
    async def cancel_task(task_id: str):
        success = await a2a_server.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel task")
        return {"status": "canceled"}

    # ─── MCP Endpoints ───────────────────────────────────────────────────────

    @app.post("/mcp/tools/list", dependencies=[Depends(_verify_api_key)])
    async def list_tools():
        return {"tools": mcp_server.list_tools()}

    class ToolCallRequest(BaseModel):
        name: str
        arguments: dict[str, Any] = {}

    @app.post("/mcp/tools/call", dependencies=[Depends(_verify_api_key)])
    async def call_tool(request: ToolCallRequest):
        return await mcp_server.call_tool(request.name, request.arguments)

    # ─── Health / Readiness ──────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "0.4.0"}

    @app.get("/ready")
    async def readiness():
        checks: dict[str, str] = {}
        try:
            if db:
                await db.get_stats()
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"

        try:
            if llm:
                available = await llm.is_available()
                checks["ollama"] = "ok" if available else "unavailable"
            else:
                checks["ollama"] = "not configured"
        except Exception as e:
            checks["ollama"] = f"error: {e}"

        all_ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "ready" if all_ok else "degraded", "checks": checks},
        )

    # ─── Status API ──────────────────────────────────────────────────────────

    # ─── Jobs API (per-job results) ──────────────────────────────────────────

    @app.get("/jobs")
    async def list_jobs(status: str | None = None):
        """List all tracked jobs with match/tailored data. Optional ?status= filter."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        if status:
            from job_agent_contracts.models import JobStatus as JS
            try:
                js = JS(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
            return await db.get_jobs_by_status(js)
        return await db.get_all_jobs_detailed()

    @app.get("/jobs/{job_id}")
    async def get_job_detail(job_id: str):
        """Get full details for a single job (match scores, cover letter, etc.)."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        all_jobs = await db.get_all_jobs_detailed()
        for job in all_jobs:
            if job["id"] == job_id:
                return job
        raise HTTPException(status_code=404, detail="Job not found")

    # ─── Outcome Tracking & Analytics ────────────────────────────────────────

    class OutcomeRequest(BaseModel):
        outcome: str  # callback, interview, offer, rejected, no_response

    @app.post("/jobs/{job_id}/outcome")
    async def record_outcome(job_id: str, request: OutcomeRequest):
        """Record an application outcome (callback/interview/offer/rejected/no_response)."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        valid = {"callback", "interview", "offer", "rejected", "no_response"}
        if request.outcome not in valid:
            raise HTTPException(status_code=400, detail=f"Invalid outcome. Must be one of: {valid}")
        await db.record_outcome(job_id, request.outcome)
        # Auto-schedule follow-up for 7 days after applying if no response yet
        return {"status": "recorded", "job_id": job_id, "outcome": request.outcome}

    @app.get("/analytics")
    async def get_analytics():
        """Get success rate analytics by source, score range, etc."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        return await db.get_success_analytics()

    @app.get("/follow-ups")
    async def get_follow_ups():
        """Get applications due for follow-up."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        return await db.get_due_follow_ups()

    # ─── Interview Prep ──────────────────────────────────────────────────────

    @app.post("/interview-prep/{job_id}")
    async def generate_interview_prep(job_id: str):
        """Generate interview questions and answers for a specific job."""
        if not db or not llm:
            raise HTTPException(status_code=503, detail="Services not initialized")
        all_jobs = await db.get_all_jobs_detailed()
        job_data = next((j for j in all_jobs if j["id"] == job_id), None)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        match_data = json.loads(job_data.get("match_data", "{}")) if job_data.get("match_data") else {}

        from job_agent_services.interview import InterviewPrepGenerator
        from job_agent_services.stores.rag import RAGService
        prep = InterviewPrepGenerator(llm=llm)
        result = await prep.generate(
            job_title=job_data["title"],
            company=job_data["company"],
            description=job_data.get("description", "") or "",
            matched_skills=match_data.get("matched_skills", []),
            missing_skills=match_data.get("missing_skills", []),
        )
        return result

    # ─── CSV/PDF Export ──────────────────────────────────────────────────────

    @app.get("/export/csv")
    async def export_csv():
        """Export all job data as CSV."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        import csv
        import io
        from fastapi.responses import StreamingResponse

        jobs = await db.get_all_jobs_detailed()
        output = io.StringIO()
        if jobs:
            writer = csv.DictWriter(output, fieldnames=[
                "title", "company", "location", "source", "status",
                "match_score", "discovered_at", "applied_at", "url", "error",
            ])
            writer.writeheader()
            for j in jobs:
                writer.writerow({
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "location": j.get("location", ""),
                    "source": j.get("source", ""),
                    "status": j.get("status", ""),
                    "match_score": j.get("match_score", ""),
                    "discovered_at": j.get("discovered_at", ""),
                    "applied_at": j.get("applied_at", ""),
                    "url": j.get("url", ""),
                    "error": j.get("error", ""),
                })
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=job_applications.csv"},
        )

    @app.get("/export/json")
    async def export_json():
        """Export all job data as JSON (with match + tailored details)."""
        if not db:
            raise HTTPException(status_code=503, detail="Database not initialized")
        return await db.get_all_jobs_detailed()

    # ─── Status API ──────────────────────────────────────────────────────────

    from job_agent_server.status import tracker

    @app.get("/status")
    async def pipeline_status():
        """Full pipeline status: current state, recent I/O, errors."""
        return tracker.get_full_status()

    @app.get("/status/state")
    async def pipeline_state():
        """Current pipeline phase and stats only."""
        return tracker.status.to_dict()

    @app.get("/status/errors")
    async def pipeline_errors():
        """Recent errors only."""
        return {
            "count": tracker.status.stats["errors"],
            "errors": [
                {"timestamp": r.timestamp, "node": r.node, "data": r.data}
                for r in list(tracker._errors)
            ],
        }

    @app.get("/status/io")
    async def pipeline_io(limit: int = 50):
        """Recent raw input/output log."""
        records = list(tracker._io_log)[-limit:]
        return {
            "count": len(records),
            "records": [
                {
                    "timestamp": r.timestamp,
                    "node": r.node,
                    "direction": r.direction,
                    "data": r.data,
                    "duration_ms": r.duration_ms,
                }
                for r in records
            ],
        }

    # ─── Source Health Monitor ─────────────────────────────────────────────

    @app.get("/sources/health")
    async def source_health():
        """Get health/rate-limit status for all job sources."""
        from job_agent_services.sources.rate_limiter import source_rate_limiter
        return source_rate_limiter.health()

    @app.get("/sources/health/{source_name}")
    async def source_health_detail(source_name: str):
        """Get health status for a specific source."""
        from job_agent_services.sources.rate_limiter import source_rate_limiter
        return source_rate_limiter.source_health(source_name)

    # ─── WebSocket Live Updates ──────────────────────────────────────────────

    _ws_clients: set[WebSocket] = set()

    async def _broadcast_ws(event: str, data: dict) -> None:
        """Send event to all connected WebSocket clients."""
        if not _ws_clients:
            return
        message = json.dumps({"event": event, "data": data, "timestamp": time.time()})
        disconnected = set()
        for ws in _ws_clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        _ws_clients -= disconnected

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time pipeline status updates."""
        await websocket.accept()
        _ws_clients.add(websocket)
        try:
            # Send current status on connect
            await websocket.send_text(json.dumps({
                "event": "connected",
                "data": tracker.get_full_status(),
                "timestamp": time.time(),
            }))
            # Keep alive — listen for pings or disconnection
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    if msg == "ping":
                        await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
                except asyncio.TimeoutError:
                    # Send heartbeat with current status
                    await websocket.send_text(json.dumps({
                        "event": "heartbeat",
                        "data": {"phase": tracker.status.phase if hasattr(tracker.status, 'phase') else "idle"},
                        "timestamp": time.time(),
                    }))
        except WebSocketDisconnect:
            pass
        finally:
            _ws_clients.discard(websocket)

    # Expose broadcast function for status tracker to use
    app.state.ws_broadcast = _broadcast_ws

    # ─── Graph Visualization & Interrupt Handler ────────────────────────────

    # Cache graph builds - avoids rebuilding on every /graph request
    _cached_graph = None
    _cached_mermaid: str | None = None

    def _get_display_graph():
        nonlocal _cached_graph, _cached_mermaid
        if _cached_graph is None:
            from job_agent_agents.workflows.graph import build_graph
            orchestrator = mcp_server.orchestrator
            _cached_graph = build_graph(
                orchestrator.search_agent, orchestrator.matcher_agent,
                orchestrator.resume_agent, orchestrator.apply_agent, orchestrator.db,
            )
            try:
                _cached_mermaid = _cached_graph.get_graph().draw_mermaid()
            except Exception:
                _cached_mermaid = _static_mermaid()
        return _cached_graph

    @app.get("/graph")
    async def get_graph():
        """Get the LangGraph workflow as a Mermaid diagram."""
        _get_display_graph()
        return {"mermaid": _cached_mermaid or _static_mermaid()}

    @app.get("/graph/nodes")
    async def get_graph_nodes():
        """List all workflow nodes with their edges."""
        graph = _get_display_graph()
        g = graph.get_graph()
        nodes = [
            {"id": node.id, "name": node.name}
            for node in g.nodes.values()
            if node.id not in ("__start__", "__end__")
        ]
        edges = [
            {"source": e.source, "target": e.target, "conditional": e.conditional}
            for e in g.edges
        ]
        return {"nodes": nodes, "edges": edges}

    @app.get("/graph/png")
    async def get_graph_png():
        """Get the graph as PNG image bytes (base64 encoded)."""
        import base64
        graph = _get_display_graph()
        try:
            png_bytes = graph.get_graph().draw_mermaid_png()
            return {"image": base64.b64encode(png_bytes).decode()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PNG generation failed: {e}")

    class InterruptResumeRequest(BaseModel):
        thread_id: str = "pipeline-run"
        approved: list[int] = []
        rejected: list[int] = []

    @app.post("/graph/resume", dependencies=[Depends(_verify_api_key)])
    async def resume_interrupted_graph(request: InterruptResumeRequest):
        """Resume an interrupted graph (human-in-the-loop approval).

        When the graph hits the human_review node with auto_submit=false,
        it pauses via interrupt(). This endpoint resumes it with the human decision.
        """
        from job_agent_agents.workflows.graph import build_graph
        orchestrator = mcp_server.orchestrator
        graph = build_graph(
            orchestrator.search_agent, orchestrator.matcher_agent,
            orchestrator.resume_agent, orchestrator.apply_agent, orchestrator.db,
        )
        config = {"configurable": {"thread_id": request.thread_id}}
        human_decision = {"approved": request.approved, "rejected": request.rejected}

        try:
            from langgraph.types import Command
            result = await graph.ainvoke(
                Command(resume=human_decision), config=config
            )
            return {
                "status": "resumed",
                "applied_count": result.get("applied_count", 0),
                "failed_count": result.get("failed_count", 0),
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Resume failed: {e}")

    @app.get("/graph/interrupted")
    async def get_interrupted_state():
        """Check if there's a graph waiting for human review."""
        from job_agent_agents.workflows.graph import build_graph
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        orchestrator = mcp_server.orchestrator
        graph = build_graph(
            orchestrator.search_agent, orchestrator.matcher_agent,
            orchestrator.resume_agent, orchestrator.apply_agent, orchestrator.db,
        )
        config = {"configurable": {"thread_id": "pipeline-run"}}
        try:
            state = await graph.aget_state(config)
            if state and state.next:
                # Graph is paused at a node
                return {
                    "interrupted": True,
                    "paused_at": list(state.next),
                    "values": {
                        "jobs_to_apply": len(state.values.get("jobs_to_apply", [])),
                        "matched_jobs": len(state.values.get("matched_jobs", [])),
                    },
                }
            return {"interrupted": False}
        except Exception:
            return {"interrupted": False}

    # ─── Webhooks ────────────────────────────────────────────────────────────

    from job_agent_server.webhooks.router import router as webhook_router, set_orchestrator
    set_orchestrator(mcp_server.orchestrator)
    app.include_router(webhook_router, dependencies=[Depends(_verify_api_key)])

    # ─── Profile / Resume Upload ─────────────────────────────────────────────

    from fastapi import File, UploadFile
    from pathlib import Path
    import shutil

    @app.post("/profile/upload", dependencies=[Depends(_verify_api_key)])
    async def upload_resume(file: UploadFile = File(...)):
        """Upload a resume PDF to seed the profile and RAG store."""
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")

        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        resume_path = data_dir / "resume.pdf"

        with open(resume_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Parse profile from resume
        try:
            from job_agent_services.profile.manager import ProfileManager
            pm = ProfileManager(llm=llm, rag=None)
            profile = await pm.ensure_profile(str(resume_path))
            return {
                "status": "uploaded",
                "path": str(resume_path),
                "profile": profile,
            }
        except Exception as e:
            return {
                "status": "uploaded_but_parse_failed",
                "path": str(resume_path),
                "error": str(e),
            }

    @app.get("/profile")
    async def get_profile():
        """Get current user profile."""
        from job_agent_services.profile.manager import ProfileManager
        pm = ProfileManager(llm=llm, rag=None)
        profile = pm.get_profile()
        if not profile:
            raise HTTPException(status_code=404, detail="No profile found. Upload a resume first.")
        return profile

    # ─── Jobs API ────────────────────────────────────────────────────────────

    @app.get("/jobs")
    async def list_jobs(status: str = ""):
        """List discovered jobs, optionally filtered by status."""
        from job_agent_contracts.models import JobStatus
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        if status:
            try:
                job_status = JobStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {[s.value for s in JobStatus]}")
            return await db.get_jobs_by_status(job_status)
        # Return all
        stats = await db.get_stats()
        all_jobs = []
        for s in JobStatus:
            all_jobs.extend(await db.get_jobs_by_status(s))
        return {"total": stats["total_discovered"], "jobs": all_jobs}

    @app.get("/jobs/stats")
    async def jobs_stats():
        """Get job application statistics."""
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        return await db.get_stats()

    # ─── Scraper Endpoints ───────────────────────────────────────────────────

    from job_agent_services.sources.remoteok import RemoteOKSource
    from job_agent_services.sources.remotive import RemotiveSource
    from job_agent_services.sources.remoterocketship import RemoteRocketshipSource

    _sources = {
        "remoteok": RemoteOKSource(),
        "remotive": RemotiveSource(),
        "remoterocketship": RemoteRocketshipSource(),
    }

    @app.get("/scrape/sources")
    async def list_sources():
        """List all available job scraping sources."""
        return {
            "sources": [
                {"name": name, "type": src.__class__.__name__}
                for name, src in _sources.items()
            ]
        }

    @app.get("/scrape/{source_name}")
    async def scrape_source(
        source_name: str,
        title: str = "software engineer",
        location: str = "Remote",
    ):
        """Run a specific scraper and return raw results.

        Query params:
          - title: job title to search (default: "software engineer")
          - location: location filter (default: "Remote")
        """
        source = _sources.get(source_name)
        if source is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown source '{source_name}'. Available: {list(_sources.keys())}",
            )

        try:
            jobs = await source.search(title, location)
            return {
                "source": source_name,
                "query": {"title": title, "location": location},
                "count": len(jobs),
                "jobs": [
                    {
                        "id": j.id,
                        "title": j.title,
                        "company": j.company,
                        "location": j.location,
                        "url": j.url,
                        "source": j.source.value if hasattr(j.source, "value") else str(j.source),
                        "tags": j.tags,
                        "salary_min": j.salary_min,
                        "salary_max": j.salary_max,
                    }
                    for j in jobs
                ],
            }
        except Exception as e:
            logger.error("Scrape %s failed: %s", source_name, e)
            raise HTTPException(status_code=500, detail=f"Scrape failed: {e}")

    @app.post("/scrape/all", dependencies=[Depends(_verify_api_key)])
    async def scrape_all(
        title: str = "software engineer",
        location: str = "Remote",
    ):
        """Run all scrapers in parallel and return combined results."""
        import asyncio

        async def _run(name: str, src):
            try:
                jobs = await src.search(title, location)
                return name, jobs, None
            except Exception as e:
                return name, [], str(e)

        tasks = [_run(name, src) for name, src in _sources.items()]
        results = await asyncio.gather(*tasks)

        combined = []
        per_source = {}
        for name, jobs, error in results:
            per_source[name] = {"count": len(jobs), "error": error}
            for j in jobs:
                combined.append({
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "url": j.url,
                    "source": name,
                    "tags": j.tags,
                })

        return {
            "query": {"title": title, "location": location},
            "total": len(combined),
            "per_source": per_source,
            "jobs": combined,
        }

    return app


def _static_mermaid() -> str:
    """Fallback static Mermaid diagram of the pipeline graph."""
    return """graph TD
    __start__([Start]) --> search
    search --> fetch_details
    fetch_details --> match
    match -->|has matches| tailor
    match -->|no matches| __end__([End])
    tailor --> human_review
    human_review -->|approved| apply
    human_review -->|rejected| __end__
    apply --> __end__

    style search fill:#4CAF50,color:white
    style match fill:#2196F3,color:white
    style tailor fill:#FF9800,color:white
    style human_review fill:#9C27B0,color:white
    style apply fill:#F44336,color:white
"""
