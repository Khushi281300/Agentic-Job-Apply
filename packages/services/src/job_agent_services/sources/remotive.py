"""Remotive job source - free API, no auth required.

Fetches remote job listings from https://remotive.com/api/remote-jobs
"""

import logging
from typing import Any
from datetime import datetime

from job_agent_contracts.interfaces import JobSource
from job_agent_contracts.models import JobListing, JobSourceType
from job_agent_services.http.client import http_client
from job_agent_services.sources.utils import rate_limited_request, location_matches

logger = logging.getLogger(__name__)

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
SOURCE_TYPE = JobSourceType.OTHER


class RemotiveSource(JobSource):
    """Remotive.com job source - free JSON API."""

    @property
    def name(self) -> str:
        return "remotive"

    async def search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Search Remotive for jobs matching title keywords."""
        try:
            url = f"{REMOTIVE_API}?search={title.replace(' ', '+')}"

            async with rate_limited_request(self.name):
                response = await http_client.get_json(url)

            if not isinstance(response, dict) or "jobs" not in response:
                logger.warning("Remotive returned unexpected response")
                return []

            jobs: list[JobListing] = []
            for item in response["jobs"]:
                try:
                    loc = item.get("candidate_required_location", "Worldwide")

                    if not location_matches(loc, location):
                        continue

                    job = JobListing(
                        id=f"remotive_{item['id']}",
                        title=item.get("title", "Unknown"),
                        company=item.get("company_name", "Unknown"),
                        location=loc or "Remote",
                        url=item.get("url", ""),
                        source=SOURCE_TYPE,
                        description=item.get("description", ""),
                        tags=item.get("tags", []),
                        discovered_at=datetime.now(),
                    )
                    jobs.append(job)
                except Exception as e:
                    logger.debug("Skipping malformed Remotive entry: %s", e)

            logger.info("Remotive: found %d jobs for '%s'", len(jobs), title)
            return jobs

        except Exception as e:
            logger.error("Remotive search failed: %s", e)
            return []

    async def fetch_details(self, url: str) -> str:
        """Fetch full job description from Remotive."""
        try:
            html = await http_client.get(url)
            return html[:5000] if html else ""
        except Exception as e:
            logger.error("Remotive fetch_details failed: %s", e)
            return ""
