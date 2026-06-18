"""Server entry point - starts FastAPI with uvicorn."""

import asyncio
import logging
import sys

import uvicorn

from job_agent_agents.container import build_container
from job_agent_agents.workflows.nodes import set_status_tracker
from job_agent_server.app import create_api_app
from job_agent_server.mcp.handler import MCPServer
from job_agent_server.a2a.handler import A2AServer
from job_agent_server.status import tracker


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the server."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    container = build_container()

    # Run startup
    asyncio.run(container.startup())

    # Wire status tracker into the node factory
    set_status_tracker(tracker)

    orchestrator = container.orchestrator

    # Build protocol servers
    mcp_server = MCPServer(orchestrator)
    a2a_server = A2AServer([
        orchestrator.search_agent,
        orchestrator.matcher_agent,
        orchestrator.resume_agent,
        orchestrator.apply_agent,
        orchestrator,
    ])

    app = create_api_app(
        mcp_server=mcp_server,
        a2a_server=a2a_server,
        db=container.db,
        llm=container.llm,
    )

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    main(port=port)
