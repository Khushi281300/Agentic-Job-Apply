"""MCP (Model Context Protocol) Server - exposes agent capabilities as MCP tools."""

import json
import logging
from typing import Any

from job_agent_contracts.models import JobListing, JobSourceType

logger = logging.getLogger(__name__)


class MCPToolDefinition:
    def __init__(self, name: str, description: str, input_schema: dict, handler):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPServer:
    """MCP-compliant server wrapping our job application agents."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self._tools: list[MCPToolDefinition] = []
        self._register_tools()

    def _register_tools(self) -> None:
        self._tools = [
            MCPToolDefinition(
                name="search_jobs",
                description="Search for job listings matching specified criteria.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "titles": {"type": "array", "items": {"type": "string"}},
                        "locations": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=self._handle_search_jobs,
            ),
            MCPToolDefinition(
                name="match_job",
                description="Score how well a specific job matches the user's profile.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_url": {"type": "string"},
                        "job_title": {"type": "string"},
                        "company": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["job_title", "company", "description"],
                },
                handler=self._handle_match_job,
            ),
            MCPToolDefinition(
                name="generate_cover_letter",
                description="Generate a tailored cover letter for a specific job.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_title": {"type": "string"},
                        "company": {"type": "string"},
                        "description": {"type": "string"},
                        "requirements": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["job_title", "company", "description"],
                },
                handler=self._handle_generate_cover_letter,
            ),
            MCPToolDefinition(
                name="get_application_stats",
                description="Get statistics about job applications.",
                input_schema={"type": "object", "properties": {}},
                handler=self._handle_get_stats,
            ),
            MCPToolDefinition(
                name="apply_to_job",
                description="Submit an application to a specific job.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_url": {"type": "string"},
                        "job_title": {"type": "string"},
                        "company": {"type": "string"},
                    },
                    "required": ["job_url"],
                },
                handler=self._handle_apply,
            ),
        ]

    def list_tools(self) -> list[dict]:
        return [t.to_dict() for t in self._tools]

    async def call_tool(self, name: str, arguments: dict) -> dict[str, Any]:
        for tool in self._tools:
            if tool.name == name:
                try:
                    result = await tool.handler(arguments)
                    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
                except Exception as e:
                    logger.error("MCP tool %s failed: %s", name, e)
                    return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}

    async def _handle_search_jobs(self, args: dict) -> dict:
        if args.get("titles"):
            self.orchestrator.search_agent.titles = args["titles"]
        if args.get("locations"):
            self.orchestrator.search_agent.locations = args["locations"]
        jobs = await self.orchestrator.search_agent.run()
        return {
            "jobs_found": len(jobs),
            "jobs": [{"title": j.title, "company": j.company, "url": j.url, "location": j.location}
                     for j in jobs[:20]],
        }

    async def _handle_match_job(self, args: dict) -> dict:
        import hashlib
        job = JobListing(
            id=hashlib.sha256(args.get("job_url", args["job_title"]).encode()).hexdigest()[:16],
            title=args["job_title"],
            company=args["company"],
            location=args.get("location", "Unknown"),
            description=args["description"],
            requirements=args.get("requirements", []),
            url=args.get("job_url", ""),
            source=JobSourceType.OTHER,
        )
        match = await self.orchestrator.matcher_agent.run(job=job)
        return match.model_dump()

    async def _handle_generate_cover_letter(self, args: dict) -> dict:
        import hashlib
        requirements = args.get("requirements", [])
        if isinstance(requirements, str):
            requirements = [r.strip() for r in requirements.split(",") if r.strip()]
        job = JobListing(
            id=hashlib.sha256(args["job_title"].encode()).hexdigest()[:16],
            title=args["job_title"],
            company=args["company"],
            location=args.get("location", ""),
            description=args["description"],
            requirements=requirements,
            url="",
            source=JobSourceType.OTHER,
        )
        match = await self.orchestrator.matcher_agent.run(job=job)
        tailored = await self.orchestrator.resume_agent.run(job=job, match=match)
        return {"cover_letter": tailored.cover_letter, "summary": tailored.summary}

    async def _handle_get_stats(self, args: dict) -> dict:
        return await self.orchestrator.db.get_stats()

    async def _handle_apply(self, args: dict) -> dict:
        import hashlib
        job = JobListing(
            id=hashlib.sha256(args["job_url"].encode()).hexdigest()[:16],
            title=args.get("job_title", ""),
            company=args.get("company", ""),
            location="",
            url=args["job_url"],
            source=JobSourceType.OTHER,
        )
        job = await self.orchestrator.search_agent.fetch_job_details(job)
        match = await self.orchestrator.matcher_agent.run(job=job)
        tailored = await self.orchestrator.resume_agent.run(job=job, match=match)
        success = await self.orchestrator.apply_agent.run(job=job, match=match, resume=tailored)
        return {"success": success, "job_title": job.title, "company": job.company}
