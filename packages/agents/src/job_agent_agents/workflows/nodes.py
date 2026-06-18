"""Agent Node Factory - wraps graph nodes with retry, audit, tracing, and status tracking."""

from __future__ import annotations

import time
import logging
from typing import Any, Callable, Coroutine

from job_agent_contracts.audit import AuditEntry
from job_agent_contracts.retry import RetryConfig, RETRY_LLM, retry_async
from job_agent_services.observability.tracing import tracer

logger = logging.getLogger(__name__)

# Optional status tracker - set by server at startup
_status_tracker = None


def set_status_tracker(tracker) -> None:
    """Set the status tracker instance (called by server on startup)."""
    global _status_tracker
    _status_tracker = tracker


def create_agent_node(
    handler: Callable[[dict], Coroutine[Any, Any, dict]],
    node_name: str,
    retry_config: RetryConfig = RETRY_LLM,
    skip_if: Callable[[dict], bool] | None = None,
    input_summary_fn: Callable[[dict], dict] | None = None,
    output_summary_fn: Callable[[dict], dict] | None = None,
) -> Callable[[dict], Coroutine[Any, Any, dict]]:
    """Factory: wrap a graph node handler with retry, audit, tracing, and status."""

    async def wrapped_node(state: dict) -> dict:
        if skip_if and skip_if(state):
            logger.info("Node '%s' skipped (condition met)", node_name)
            entry = AuditEntry(
                node_name=node_name,
                status="skipped",
                metadata={"reason": "skip_if condition"},
            )
            return {"audit_trail": [entry]}

        start = time.time()
        input_summary = input_summary_fn(state) if input_summary_fn else {}

        # Record input to status tracker
        if _status_tracker:
            _status_tracker.record_input(node_name, input_summary)

        try:
            async def _execute():
                return await handler(state)

            result = await retry_async(
                _execute,
                config=retry_config,
                operation_name=f"node.{node_name}",
            )

            duration = (time.time() - start) * 1000
            output_summary = output_summary_fn(result) if output_summary_fn else {}

            # Record output to status tracker
            if _status_tracker:
                _status_tracker.record_output(node_name, output_summary)

            entry = AuditEntry(
                node_name=node_name,
                status="success",
                duration_ms=duration,
                input_summary=input_summary,
                output_summary=output_summary,
            )
            existing = result.get("audit_trail", [])
            result["audit_trail"] = existing + [entry]
            return result

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error("Node '%s' failed permanently: %s", node_name, e)

            # Record error to status tracker
            if _status_tracker:
                _status_tracker.record_error(node_name, e)

            entry = AuditEntry(
                node_name=node_name,
                status="failed",
                duration_ms=duration,
                input_summary=input_summary,
                error=str(e),
                retry_count=retry_config.max_retries,
            )
            return {
                "errors": [f"{node_name}: {e}"],
                "audit_trail": [entry],
            }

    wrapped_node.__name__ = f"node_{node_name}"
    wrapped_node.__qualname__ = f"create_agent_node.<locals>.node_{node_name}"
    return wrapped_node
