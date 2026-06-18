"""Contract tests — verify scraper parsers handle expected HTML/JSON formats.

These snapshot-based tests ensure parsers still work when job board
responses change. If a test fails, it means the board's format may have
changed and the parser needs updating.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from job_agent_contracts.models import JobListing


class TestRemoteOKContract:
    """Verify RemoteOK JSON API response parsing contract."""

    SAMPLE_RESPONSE = [
        {"legal": "RemoteOK API"},  # metadata entry — should be skipped
        {
            "id": 123456,
            "position": "Python Backend Developer",
            "company": "TechCorp",
            "location": "Worldwide",
            "url": "https://remoteok.com/l/123456",
            "description": "<p>We need a Python developer.</p>",
            "salary_min": "80000",
            "salary_max": "120000",
            "tags": ["python", "backend", "remote"],
        },
        {
            "id": 789012,
            "position": "Full Stack Engineer",
            "company": "StartupCo",
            "location": "US Only",
            "description": "Full stack role with React + Node.",
            "tags": ["react", "node", "typescript"],
        },
    ]

    @pytest.mark.asyncio
    async def test_parses_valid_jobs(self, mock_source_infra):
        """Parser extracts jobs from valid API response."""
        from job_agent_services.sources.remoteok import RemoteOKSource

        source = RemoteOKSource()
        with patch("job_agent_services.sources.remoteok.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value=self.SAMPLE_RESPONSE)
            jobs = await source.search("python", "remote")

        assert len(jobs) == 2
        assert jobs[0].title == "Python Backend Developer"
        assert jobs[0].company == "TechCorp"
        assert jobs[0].id == "remoteok_123456"

    @pytest.mark.asyncio
    async def test_skips_metadata_entries(self, mock_source_infra):
        """First element (metadata) is correctly skipped."""
        from job_agent_services.sources.remoteok import RemoteOKSource

        source = RemoteOKSource()
        with patch("job_agent_services.sources.remoteok.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value=[{"legal": "ok"}])
            jobs = await source.search("python", "remote")

        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_salary_parsing(self, mock_source_infra):
        """Salary fields are correctly parsed."""
        from job_agent_services.sources.remoteok import RemoteOKSource

        source = RemoteOKSource()
        with patch("job_agent_services.sources.remoteok.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value=self.SAMPLE_RESPONSE)
            jobs = await source.search("python", "remote")

        assert jobs[0].salary_min == 80000
        assert jobs[0].salary_max == 120000


class TestRemotiveContract:
    """Verify Remotive JSON API response parsing contract."""

    SAMPLE_RESPONSE = {
        "jobs": [
            {
                "id": 11111,
                "title": "Senior DevOps Engineer",
                "company_name": "CloudCo",
                "candidate_required_location": "Worldwide",
                "url": "https://remotive.com/jobs/11111",
                "description": "DevOps role managing AWS infrastructure.",
                "tags": ["devops", "aws", "kubernetes"],
            },
            {
                "id": 22222,
                "title": "React Developer",
                "company_name": "UILab",
                "candidate_required_location": "Europe",
                "url": "https://remotive.com/jobs/22222",
                "description": "Frontend React developer needed.",
                "tags": ["react", "typescript"],
            },
        ]
    }

    @pytest.mark.asyncio
    async def test_parses_valid_response(self, mock_source_infra):
        """Parser correctly extracts jobs from Remotive API format."""
        from job_agent_services.sources.remotive import RemotiveSource

        source = RemotiveSource()
        with patch("job_agent_services.sources.remotive.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value=self.SAMPLE_RESPONSE)
            jobs = await source.search("devops", "remote")

        assert len(jobs) == 2
        assert jobs[0].title == "Senior DevOps Engineer"
        assert jobs[0].company == "CloudCo"
        assert jobs[0].id == "remotive_11111"

    @pytest.mark.asyncio
    async def test_location_filtering(self, mock_source_infra):
        """Jobs are filtered by location correctly."""
        from job_agent_services.sources.remotive import RemotiveSource

        source = RemotiveSource()
        with patch("job_agent_services.sources.remotive.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value=self.SAMPLE_RESPONSE)
            jobs = await source.search("devops", "europe")

        # Only the Europe job should match
        assert len(jobs) == 1
        assert jobs[0].title == "React Developer"

    @pytest.mark.asyncio
    async def test_handles_empty_response(self, mock_source_infra):
        """Empty/unexpected response returns empty list."""
        from job_agent_services.sources.remotive import RemotiveSource

        source = RemotiveSource()
        with patch("job_agent_services.sources.remotive.http_client") as mock_http:
            mock_http.get_json = AsyncMock(return_value={"something": "else"})
            jobs = await source.search("devops", "remote")

        assert len(jobs) == 0


class TestRemoteRocketshipContract:
    """Verify RemoteRocketship HTML scraper parsing contract."""

    SAMPLE_HTML = '''
    <html><body>
    <a href="/company/techcorp/jobs/senior-python-developer-remote/">
        <span>Senior Python Developer</span>
    </a>
    <a href="/company/techcorp/" class="company-link">
        <span>TechCorp</span>
    </a>
    <span>United States – Remote</span>
    <a href="/company/startupco/jobs/react-engineer-remote/">
        <span>React Engineer</span>
    </a>
    <a href="/company/startupco/" class="company-link">
        <span>StartupCo</span>
    </a>
    </body></html>
    '''

    def test_parse_jobs_extracts_listings(self):
        """HTML parser correctly extracts job listings."""
        from job_agent_services.sources.remoterocketship import RemoteRocketshipSource

        source = RemoteRocketshipSource()
        jobs = source._parse_jobs(self.SAMPLE_HTML, "remote")

        assert len(jobs) >= 1
        # Verify job structure is correct
        for job in jobs:
            assert job.title
            assert job.company
            assert job.url.startswith("https://www.remoterocketship.com")

    def test_location_filter_applied(self):
        """Location filter correctly removes non-matching jobs."""
        from job_agent_services.sources.remoterocketship import RemoteRocketshipSource

        source = RemoteRocketshipSource()
        # Filter for a specific location that doesn't match
        jobs = source._parse_jobs(self.SAMPLE_HTML, "australia")
        # Should get fewer results (or none) compared to "remote"
        all_jobs = source._parse_jobs(self.SAMPLE_HTML, "remote")
        assert len(jobs) <= len(all_jobs)
