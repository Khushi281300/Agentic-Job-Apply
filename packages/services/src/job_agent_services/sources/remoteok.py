"""RemoteOK job source - free API, no auth required.

Fetches remote job listings from https://remoteok.com/api
"""

import logging
from typing import Any
from datetime import datetime

from job_agent_contracts.models import JobListing, JobSourceType
from job_agent_services.http.client import http_client
from job_agent_services.sources.base_source import BaseJobSource
from job_agent_services.sources.utils import rate_limited_request, location_matches

logger = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"
SOURCE_TYPE = JobSourceType.REMOTE_OK


class RemoteOKSource(BaseJobSource):
    """RemoteOK.com job source - free JSON API."""

    @property
    def name(self) -> str:
        return "remoteok"

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Fetch and parse RemoteOK API results."""
        tag = title.lower().replace(" ", "-")
        url = f"{REMOTEOK_API}?tag={tag}"

        async with rate_limited_request(self.name):
            response = await http_client.get_json(url)

        if not isinstance(response, list):
            logger.warning("RemoteOK returned unexpected response type")
            return []

        jobs = self._parse_items(
            response,
            lambda item: self._parse_one(item, location),
        )
        logger.info("RemoteOK: found %d jobs for '%s'", len(jobs), title)
        return jobs

    async def _do_fetch_details(self, url: str) -> str:
        """Fetch full job description from RemoteOK page."""
        html = await http_client.get(url)
        return html[:5000] if html else ""

    def _parse_one(self, item: Any, location: str) -> JobListing | None:
        """Parse a single API item into a JobListing or None to skip."""
        if not isinstance(item, dict) or "id" not in item:
            return None

        loc = item.get("location", "Worldwide")
        if not location_matches(loc, location):
            return None

        return JobListing(
            id=f"remoteok_{item['id']}",
            title=item.get("position", "Unknown"),
            company=item.get("company", "Unknown"),
            location=loc or "Remote",
            url=item.get("url", f"https://remoteok.com/l/{item['id']}"),
            source=SOURCE_TYPE,
            description=item.get("description", ""),
            salary_min=self._parse_salary(item.get("salary_min")),
            salary_max=self._parse_salary(item.get("salary_max")),
            tags=item.get("tags", []),
            discovered_at=datetime.now(),
        )

    @staticmethod
    def _parse_salary(value: Any) -> int:
        """Parse salary value from API response."""
        if value is None:
            return 0
        try:
            return int(str(value).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return 0
