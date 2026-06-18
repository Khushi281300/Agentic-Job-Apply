"""LangSmith tracing and observability integration.

Provides:
- Automatic tracing of all LLM calls
- Parent-child span hierarchy
- Latency tracking
- Works locally when LangSmith is disabled
"""

import functools
import logging
import os
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


class TraceSpan:
    """A single trace span representing an operation."""

    def __init__(self, name: str, parent_id: str | None = None, metadata: dict | None = None):
        self.id = str(uuid4())
        self.name = name
        self.parent_id = parent_id
        self.metadata = metadata or {}
        self.start_time = time.time()
        self.end_time: float | None = None
        self.status: str = "running"
        self.inputs: dict = {}
        self.outputs: dict = {}
        self.error: str = ""
        self.events: list[dict] = []

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

    def finish(self, status: str = "success", outputs: dict | None = None) -> None:
        self.end_time = time.time()
        self.status = status
        if outputs:
            self.outputs = outputs

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error": self.error,
            "events": self.events,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
        }


class LangSmithTracer:
    """LangSmith-compatible tracer for observability.

    When LANGSMITH_API_KEY is set, traces are sent to LangSmith.
    Otherwise, traces are stored locally for debugging.
    """

    def __init__(self):
        self._enabled = False
        self._client = None
        self._project = "job-apply-agent"
        self._spans: list[TraceSpan] = []
        self._active_span: TraceSpan | None = None

    def configure(self, api_key: str = "", project: str = "", enabled: bool = False) -> None:
        """Configure LangSmith integration."""
        self._enabled = enabled and bool(api_key)
        self._project = project or "job-apply-agent"

        if self._enabled:
            try:
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                os.environ["LANGCHAIN_API_KEY"] = api_key
                os.environ["LANGCHAIN_PROJECT"] = self._project

                from langsmith import Client
                self._client = Client(api_key=api_key)
                logger.info("LangSmith tracing enabled (project: %s)", self._project)
            except ImportError:
                logger.warning("langsmith package not found, tracing disabled")
                self._enabled = False
            except Exception as e:
                logger.warning("LangSmith init failed: %s", e)
                self._enabled = False
        else:
            logger.info("LangSmith tracing disabled (local-only mode)")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @contextmanager
    def span(self, name: str, metadata: dict | None = None, inputs: dict | None = None):
        """Create a trace span (synchronous context manager)."""
        parent = self._active_span
        span = TraceSpan(name=name, parent_id=parent.id if parent else None, metadata=metadata)
        span.inputs = inputs or {}
        self._active_span = span

        try:
            yield span
            span.finish("success")
        except Exception as e:
            span.error = str(e)
            span.finish("error")
            raise
        finally:
            self._spans.append(span)
            self._active_span = parent
            self._send_span(span)

    @asynccontextmanager
    async def aspan(self, name: str, metadata: dict | None = None, inputs: dict | None = None):
        """Create a trace span (async context manager)."""
        parent = self._active_span
        span = TraceSpan(name=name, parent_id=parent.id if parent else None, metadata=metadata)
        span.inputs = inputs or {}
        self._active_span = span

        try:
            yield span
            span.finish("success")
        except Exception as e:
            span.error = str(e)
            span.finish("error")
            raise
        finally:
            self._spans.append(span)
            self._active_span = parent
            self._send_span(span)

    def _send_span(self, span: TraceSpan) -> None:
        """Send span to LangSmith (or log locally)."""
        if self._enabled and self._client:
            try:
                self._client.create_run(
                    name=span.name,
                    run_type="chain",
                    inputs=span.inputs,
                    outputs=span.outputs,
                    error=span.error or None,
                    start_time=datetime.fromtimestamp(span.start_time),
                    end_time=datetime.fromtimestamp(span.end_time) if span.end_time else None,
                    extra=span.metadata,
                    project_name=self._project,
                    parent_run_id=span.parent_id,
                    id=span.id,
                )
            except Exception as e:
                logger.debug("Failed to send span to LangSmith: %s", e)
        else:
            logger.debug("Trace: %s [%s] %.0fms", span.name, span.status, span.duration_ms)

    def get_traces(self, limit: int = 50) -> list[dict]:
        """Get recent trace spans (local)."""
        return [s.to_dict() for s in self._spans[-limit:]]

    def get_stats(self) -> dict:
        """Get tracing statistics."""
        total = len(self._spans)
        errors = sum(1 for s in self._spans if s.status == "error")
        avg_duration = (
            sum(s.duration_ms for s in self._spans) / total if total > 0 else 0
        )
        return {
            "total_spans": total,
            "errors": errors,
            "avg_duration_ms": round(avg_duration, 1),
            "langsmith_enabled": self._enabled,
            "project": self._project,
        }


def trace_agent(agent_name: str):
    """Decorator to trace an async agent function."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with tracer.aspan(
                f"agent.{agent_name}.{func.__name__}",
                metadata={"agent": agent_name},
                inputs={"args_count": len(args), "kwargs_keys": list(kwargs.keys())},
            ) as span:
                result = await func(*args, **kwargs)
                if isinstance(result, dict):
                    span.outputs = result
                return result
        return wrapper
    return decorator


# Global tracer singleton
tracer = LangSmithTracer()
