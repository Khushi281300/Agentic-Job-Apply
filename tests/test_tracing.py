"""Tests for tracing service."""

import pytest
from job_agent_services.observability.tracing import LangSmithTracer, TraceSpan


class TestTraceSpan:
    def test_create_span(self):
        span = TraceSpan(name="test_op")
        assert span.name == "test_op"
        assert span.status == "running"
        assert span.parent_id is None

    def test_finish_span(self):
        span = TraceSpan(name="test_op")
        span.finish("success", outputs={"key": "val"})
        assert span.status == "success"
        assert span.duration_ms > 0
        assert span.outputs == {"key": "val"}

    def test_span_to_dict(self):
        span = TraceSpan(name="op", metadata={"model": "llama3"})
        span.finish()
        d = span.to_dict()
        assert d["name"] == "op"
        assert d["metadata"]["model"] == "llama3"
        assert "start_time" in d


class TestLangSmithTracer:
    def test_disabled_by_default(self):
        t = LangSmithTracer()
        assert not t.is_enabled

    def test_configure_without_key(self):
        t = LangSmithTracer()
        t.configure(api_key="", project="test", enabled=True)
        assert not t.is_enabled  # No key = disabled

    @pytest.mark.asyncio
    async def test_aspan_records(self):
        t = LangSmithTracer()
        async with t.aspan("test_span", inputs={"x": 1}) as span:
            span.outputs = {"y": 2}

        traces = t.get_traces()
        assert len(traces) == 1
        assert traces[0]["name"] == "test_span"
        assert traces[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_aspan_error(self):
        t = LangSmithTracer()
        with pytest.raises(ValueError):
            async with t.aspan("bad") as span:
                raise ValueError("boom")

        traces = t.get_traces()
        assert traces[0]["status"] == "error"
        assert "boom" in traces[0]["error"]

    def test_get_stats(self):
        t = LangSmithTracer()
        stats = t.get_stats()
        assert stats["total_spans"] == 0
        assert stats["langsmith_enabled"] is False
