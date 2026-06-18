"""Base job source class — shared error handling and item parsing.

All job sources inherit from this instead of implementing repeated
try/except and logging patterns individually.
"""

import logging
from typing import Any, Callable

from job_agent_contracts.interfaces import JobSource
from job_agent_contracts.models import JobListing

logger = logging.getLogger(__name__)


class BaseJobSource(JobSource):
    """Base class with reusable search/parse error handling.

    Subclasses implement:
        - _do_search(title, location, **kwargs) → list[JobListing]
        - _do_fetch_details(url) → str
    """

    async def search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Search with automatic error handling — delegates to _do_search."""
        try:
            return await self._do_search(title, location, **kwargs)
        except Exception as e:
            logger.error("%s search failed: %s", self.name, e)
            return []

    async def fetch_details(self, url: str) -> str:
        """Fetch details with automatic error handling — delegates to _do_fetch_details."""
        try:
            return await self._do_fetch_details(url)
        except Exception as e:
            logger.error("%s fetch_details failed: %s", self.name, e)
            return ""

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Override in subclass — actual search logic without try/except."""
        raise NotImplementedError

    async def _do_fetch_details(self, url: str) -> str:
        """Override in subclass — actual fetch logic without try/except."""
        raise NotImplementedError

    def _parse_items(
        self,
        items: list[Any],
        parser: Callable[[Any], JobListing | None],
    ) -> list[JobListing]:
        """Parse a list of raw items into JobListings, skipping malformed ones.

        Args:
            items: Raw items from API/HTML parsing.
            parser: Function that takes one raw item and returns a JobListing
                    or None (to skip). Raises on malformed data.
        """
        jobs: list[JobListing] = []
        for item in items:
            try:
                job = parser(item)
                if job is not None:
                    jobs.append(job)
            except Exception as e:
                logger.debug("Skipping malformed %s entry: %s", self.name, e)
        return jobs
