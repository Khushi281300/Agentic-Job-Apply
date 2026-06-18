"""Shared test fixtures — reusable mocks for source and LLM testing.

Import these in test files to avoid repeating the same mock setup everywhere.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_source_infra():
    """Pre-configured mocks for rate limiter + circuit breaker.

    Yields a dict with keys: rate_limiter, circuit_registry.

    Usage:
        async def test_something(mock_source_infra):
            source = RemoteOKSource()
            with patch("...http_client") as mock_http:
                mock_http.get_json = AsyncMock(return_value=data)
                jobs = await source.search("python", "remote")
    """
    with patch("job_agent_services.sources.utils.source_rate_limiter") as mock_rl, \
         patch("job_agent_services.sources.utils.circuit_registry") as mock_cr:
        mock_rl.acquire = AsyncMock()
        mock_rl.record_success = MagicMock()
        mock_rl.record_error = MagicMock()

        mock_breaker = MagicMock()
        mock_breaker.is_available = True
        mock_breaker.record_success = MagicMock()
        mock_breaker.record_failure = MagicMock()
        mock_cr.get = MagicMock(return_value=mock_breaker)

        yield {
            "rate_limiter": mock_rl,
            "circuit_registry": mock_cr,
            "circuit_breaker": mock_breaker,
        }


@pytest.fixture
def mock_remoteok_http():
    """Mock HTTP client for RemoteOK source."""
    with patch("job_agent_services.sources.remoteok.http_client") as mock:
        yield mock


@pytest.fixture
def mock_remotive_http():
    """Mock HTTP client for Remotive source."""
    with patch("job_agent_services.sources.remotive.http_client") as mock:
        yield mock


@pytest.fixture
def mock_llm():
    """Mock LLMProvider with all methods pre-configured.

    Usage:
        async def test_agent(mock_llm):
            mock_llm.generate_validated.return_value = MyModel(...)
            agent = MyAgent(llm=mock_llm, ...)
            result = await agent.run(...)
    """
    llm = MagicMock()
    llm.generate = AsyncMock(return_value="generated text")
    llm.generate_json = AsyncMock(return_value={})
    llm.generate_validated = AsyncMock(return_value=None)
    llm.chat = AsyncMock(return_value="chat response")
    llm.embed = AsyncMock(return_value=[0.1] * 384)
    return llm


@pytest.fixture
def mock_database():
    """Mock Database with all common methods pre-configured."""
    db = MagicMock()
    db.initialize = AsyncMock()
    db.save_job = AsyncMock()
    db.update_status = AsyncMock()
    db.update_match = AsyncMock()
    db.is_already_seen = AsyncMock(return_value=False)
    db.get_today_application_count = AsyncMock(return_value=0)
    db.record_outcome = AsyncMock()
    db.set_follow_up = AsyncMock()
    db.get_stats = AsyncMock(return_value={
        "total_discovered": 0, "applied": 0, "matched_pending": 0, "rejected": 0,
    })
    return db


@pytest.fixture
def mock_rag():
    """Mock RAGService."""
    rag = MagicMock()
    rag.get_relevant_context = AsyncMock(return_value="")
    rag.index_application = AsyncMock()
    return rag
