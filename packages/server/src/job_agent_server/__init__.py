"""Job Agent Server - HTTP server with MCP + A2A protocol endpoints."""

__version__ = "0.4.0"

from job_agent_server.app import create_api_app
from job_agent_server.mcp.handler import MCPServer
from job_agent_server.a2a.handler import A2AServer

__all__ = ["create_api_app", "MCPServer", "A2AServer"]
