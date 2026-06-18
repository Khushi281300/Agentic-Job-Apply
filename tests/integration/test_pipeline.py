"""Integration tests for the job search pipeline with mocked sources."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from job_agent_contracts.models import JobListing, JobSourceType
from job_agent_services.sources.remoteok import RemoteOKSource
from job_agent_services.sources.remotive import RemotiveSource
from job_agent_services.sources.remoterocketship import RemoteRocketshipSource


# ─── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_REMOTEOK_RESPONSE = [
    {"legal": "RemoteOK API"},  # metadata, should be skipped
    {
        "id": "12345",
        "position": "Senior Python Engineer",
        "company": "TechCorp",
        "location": "Worldwide",
        "url": "https://remoteok.com/l/12345",
        "description": "Build scalable backend systems with Python.",
        "tags": ["python", "backend", "fastapi"],
        "salary_min": "100000",
        "salary_max": "150000",
    },
    {
        "id": "12346",
        "position": "Frontend Developer",
        "company": "DesignStudio",
        "location": "USA Only",
        "url": "https://remoteok.com/l/12346",
        "description": "React and TypeScript work.",
        "tags": ["react", "typescript"],
    },
]

SAMPLE_REMOTIVE_RESPONSE = {
    "jobs": [
        {
            "id": 98765,
            "title": "Backend Engineer (Python)",
            "company_name": "DataFlow Inc",
            "candidate_required_location": "Worldwide",
            "url": "https://remotive.com/jobs/98765",
            "description": "FastAPI + PostgreSQL backend work.",
            "tags": ["python", "fastapi"],
        },
        {
            "id": 98766,
            "title": "DevOps Engineer",
            "company_name": "CloudOps",
            "candidate_required_location": "Europe",
            "url": "https://remotive.com/jobs/98766",
            "description": "Kubernetes and Terraform.",
            "tags": ["devops", "kubernetes"],
        },
    ]
}


# ─── RemoteOK Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remoteok_search_parses_jobs():
    """RemoteOK source correctly parses API response into JobListings."""
    source = RemoteOKSource()

    with patch("job_agent_services.sources.remoteok.http_client") as mock_client:
        mock_client.get_json = AsyncMock(return_value=SAMPLE_REMOTEOK_RESPONSE)

        jobs = await source.search("Python Engineer", "Remote")

        assert len(jobs) == 2
        assert jobs[0].title == "Senior Python Engineer"
        assert jobs[0].company == "TechCorp"
        assert jobs[0].id == "remoteok_12345"
        assert "python" in jobs[0].tags


@pytest.mark.asyncio
async def test_remoteok_filters_by_location():
    """RemoteOK source filters jobs by location."""
    source = RemoteOKSource()

    with patch("job_agent_services.sources.remoteok.http_client") as mock_client:
        mock_client.get_json = AsyncMock(return_value=SAMPLE_REMOTEOK_RESPONSE)

        jobs = await source.search("Developer", "USA")

        # Only "USA Only" job should match
        assert len(jobs) == 1
        assert jobs[0].company == "DesignStudio"


@pytest.mark.asyncio
async def test_remoteok_handles_api_error():
    """RemoteOK source returns empty list on error."""
    source = RemoteOKSource()

    with patch("job_agent_services.sources.remoteok.http_client") as mock_client:
        mock_client.get_json = AsyncMock(side_effect=Exception("Connection timeout"))

        jobs = await source.search("Engineer", "Remote")
        assert jobs == []


# ─── Remotive Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remotive_search_parses_jobs():
    """Remotive source correctly parses API response."""
    source = RemotiveSource()

    with patch("job_agent_services.sources.remotive.http_client") as mock_client:
        mock_client.get_json = AsyncMock(return_value=SAMPLE_REMOTIVE_RESPONSE)

        jobs = await source.search("Backend Engineer", "Remote")

        assert len(jobs) == 2
        assert jobs[0].title == "Backend Engineer (Python)"
        assert jobs[0].company == "DataFlow Inc"
        assert jobs[0].id == "remotive_98765"


@pytest.mark.asyncio
async def test_remotive_filters_by_location():
    """Remotive source filters by candidate_required_location."""
    source = RemotiveSource()

    with patch("job_agent_services.sources.remotive.http_client") as mock_client:
        mock_client.get_json = AsyncMock(return_value=SAMPLE_REMOTIVE_RESPONSE)

        jobs = await source.search("Engineer", "Europe")

        assert len(jobs) == 1
        assert jobs[0].company == "CloudOps"


@pytest.mark.asyncio
async def test_remotive_handles_empty_response():
    """Remotive source handles empty API response."""
    source = RemotiveSource()

    with patch("job_agent_services.sources.remotive.http_client") as mock_client:
        mock_client.get_json = AsyncMock(return_value={"jobs": []})

        jobs = await source.search("Nonexistent Role", "Remote")
        assert jobs == []


# ─── RemoteRocketship Tests ──────────────────────────────────────────────────

SAMPLE_ROCKETSHIP_HTML = """
<html><body>
<a href="/company/acme-corp/jobs/senior-python-developer-united-states-remote/">Senior Python Developer</a>
<a href="/company/acme-corp/">Acme Corp</a>
<a href="/company/acme-corp/">All Job Openings</a>
<a href="/company/beta-inc/jobs/frontend-engineer-brazil-remote/">Frontend Engineer</a>
<a href="/company/beta-inc/">Beta Inc</a>
<a href="/company/beta-inc/">All Job Openings</a>
</body></html>
"""


@pytest.mark.asyncio
async def test_remoterocketship_parses_html():
    """RemoteRocketship parses job cards from HTML correctly."""
    source = RemoteRocketshipSource()

    with patch("job_agent_services.sources.remoterocketship.PlaywrightBrowser") as MockBrowser:
        mock_browser = AsyncMock()
        mock_browser.get_page_content = AsyncMock(return_value=SAMPLE_ROCKETSHIP_HTML)
        mock_browser.navigate = AsyncMock()
        mock_browser.start = AsyncMock()
        mock_browser.stop = AsyncMock()
        MockBrowser.return_value = mock_browser

        jobs = await source.search("python developer", "Remote")

        assert len(jobs) == 2
        assert jobs[0].company == "Acme Corp"
        assert jobs[1].company == "Beta Inc"
        assert "remoterocketship.com" in jobs[0].url


@pytest.mark.asyncio
async def test_remoterocketship_handles_empty_page():
    """RemoteRocketship handles empty/blocked page gracefully."""
    source = RemoteRocketshipSource()

    with patch("job_agent_services.sources.remoterocketship.PlaywrightBrowser") as MockBrowser:
        mock_browser = AsyncMock()
        mock_browser.get_page_content = AsyncMock(return_value="<html></html>")
        mock_browser.navigate = AsyncMock()
        mock_browser.start = AsyncMock()
        mock_browser.stop = AsyncMock()
        MockBrowser.return_value = mock_browser

        jobs = await source.search("engineer", "Remote")
        assert jobs == []


@pytest.mark.asyncio
async def test_remoterocketship_filters_all_job_openings():
    """RemoteRocketship doesn't use 'All Job Openings' as company name."""
    source = RemoteRocketshipSource()

    with patch("job_agent_services.sources.remoterocketship.PlaywrightBrowser") as MockBrowser:
        mock_browser = AsyncMock()
        mock_browser.get_page_content = AsyncMock(return_value=SAMPLE_ROCKETSHIP_HTML)
        mock_browser.navigate = AsyncMock()
        mock_browser.start = AsyncMock()
        mock_browser.stop = AsyncMock()
        MockBrowser.return_value = mock_browser

        jobs = await source.search("developer", "Remote")

        for job in jobs:
            assert job.company != "All Job Openings"


# ─── NotificationService Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notification_service_dispatches():
    """NotificationService sends to configured channels."""
    from job_agent_services.notifications.service import NotificationService

    svc = NotificationService(
        telegram_token="fake_token",
        telegram_chat_id="123456",
    )

    assert svc.has_telegram
    assert not svc.has_slack
    assert svc.is_configured

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        await svc.notify("Test Title", "Test message", level="success")
        mock_post.assert_called_once()


# ─── Status Tracker Tests ────────────────────────────────────────────────────

def test_status_tracker_records():
    """StatusTracker records I/O and errors correctly."""
    from job_agent_server.status import StatusTracker, PipelinePhase

    t = StatusTracker()
    t.set_phase(PipelinePhase.SEARCHING)
    t.record_input("search", {"titles": ["Python"]})
    t.record_output("search", {"found": 5})
    t.record_error("match", "LLM timeout")

    status = t.get_full_status()
    assert status["pipeline"]["phase"] == "searching"
    assert status["pipeline"]["stats"]["errors"] == 1
    assert len(status["recent_io"]) == 3
    assert len(status["errors"]) == 1


# ─── Graph Build Tests ───────────────────────────────────────────────────────

def test_graph_compiles_without_checkpointer():
    """Graph compiles for visualization without async checkpointer."""
    from job_agent_agents.workflows.graph import compile_graph_for_display

    mock = MagicMock()
    graph = compile_graph_for_display(mock, mock, mock, mock, mock)

    # Should have our nodes
    node_ids = [n.id for n in graph.get_graph().nodes.values()]
    assert "search" in node_ids
    assert "match" in node_ids
    assert "tailor" in node_ids
    assert "human_review" in node_ids
    assert "apply" in node_ids


def test_graph_produces_mermaid():
    """Graph generates valid Mermaid diagram."""
    from job_agent_agents.workflows.graph import compile_graph_for_display

    mock = MagicMock()
    graph = compile_graph_for_display(mock, mock, mock, mock, mock)
    mermaid = graph.get_graph().draw_mermaid()

    assert "graph TD" in mermaid
    assert "search" in mermaid
    assert "apply" in mermaid
    assert "__end__" in mermaid
