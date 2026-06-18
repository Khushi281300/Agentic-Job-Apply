"""RemoteRocketship job source - browser scraping (Cloudflare protected).

Scrapes remote job listings from https://www.remoterocketship.com/jobs/{title}
using Playwright to bypass Cloudflare protection.
"""

import logging
import re
from typing import Any
from datetime import datetime

from job_agent_contracts.interfaces import JobSource
from job_agent_contracts.models import JobListing, JobSourceType
from job_agent_services.automation.browser import PlaywrightBrowser
from job_agent_services.sources.utils import rate_limited_request, location_matches

logger = logging.getLogger(__name__)

BASE_URL = "https://www.remoterocketship.com"

# Pre-compiled regexes for parsing (avoid recompilation per call)
_RE_JOB_URL = re.compile(r'href="(/company/([^/]+)/jobs/([^"]+))"')
_RE_COMPANY = re.compile(
    r'href="/company/([^/]+)/"[^>]*>\s*(?:<[^>]*>)*\s*([^<]+?)\s*<', re.DOTALL
)
_RE_LOCATION = re.compile(r'([A-Z][a-zA-Z\s]+)\s*[–—-]\s*Remote')
_SKIP_COMPANY_NAMES = frozenset({"all job openings", "website", "linkedin", ""})
_LOCATION_SUFFIXES = (
    "-worldwide", "-united-states", "-united-kingdom",
    "-netherlands", "-india", "-poland", "-brazil",
    "-germany", "-czechia", "-ukraine", "-argentina",
    "-mexico", "-canada", "-australia", "-france",
    "-spain", "-italy", "-philippines", "-colombia",
    "-peru", "-chile", "-ecuador", "-paraguay",
    "-uruguay", "-new-york", "-california", "-texas",
    "-virginia", "-colorado", "-pennsylvania",
)


class RemoteRocketshipSource(JobSource):
    """RemoteRocketship.com job source - Playwright scraper with browser reuse."""

    def __init__(self):
        self._browser: PlaywrightBrowser | None = None

    @property
    def name(self) -> str:
        return "remoterocketship"

    async def _get_browser(self) -> PlaywrightBrowser:
        """Reuse a single browser instance across calls."""
        if self._browser is None:
            self._browser = PlaywrightBrowser(headless=True)
            await self._browser.start()
        return self._browser

    async def close(self) -> None:
        if self._browser:
            await self._browser.stop()
            self._browser = None

    async def search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Scrape RemoteRocketship for jobs matching title using Playwright."""
        try:
            slug = title.lower().replace(" ", "-")
            url = f"{BASE_URL}/jobs/{slug}"

            async with rate_limited_request(self.name):
                browser = await self._get_browser()
                await browser.navigate(url)
                html = await browser.get_page_content()

            if not html:
                logger.warning("RemoteRocketship: empty/blocked response for '%s'", title)
                return []

            jobs = self._parse_jobs(html, location)
            logger.info("RemoteRocketship: found %d jobs for '%s'", len(jobs), title)
            return jobs

        except Exception as e:
            logger.error("RemoteRocketship search failed: %s", e)
            # Reset browser on error
            await self.close()
            return []

    async def fetch_details(self, url: str) -> str:
        """Fetch full job description from a RemoteRocketship job page."""
        try:
            browser = await self._get_browser()
            await browser.navigate(url)
            return await browser.get_page_content()
        except Exception as e:
            logger.error("RemoteRocketship fetch_details failed: %s", e)
            return ""

    def _parse_jobs(self, html: str, location_filter: str) -> list[JobListing]:
        """Parse job listings from the HTML page."""
        jobs: list[JobListing] = []

        job_urls = _RE_JOB_URL.findall(html)

        # Build company slug -> name map
        company_map: dict[str, str] = {}
        for slug, name in _RE_COMPANY.findall(html):
            name = name.strip()
            if name.lower() not in _SKIP_COMPANY_NAMES and len(name) > 1:
                company_map[slug] = name

        seen_urls: set[str] = set()
        for full_path, company_slug, job_slug in job_urls:
            if full_path in seen_urls:
                continue
            seen_urls.add(full_path)

            title_slug = job_slug
            if title_slug.endswith("-remote/"):
                title_slug = title_slug[:-8]
            elif title_slug.endswith("-remote"):
                title_slug = title_slug[:-7]

            for suffix in _LOCATION_SUFFIXES:
                if title_slug.endswith(suffix):
                    title_slug = title_slug[: -len(suffix)]
                    break

            job_title = title_slug.replace("-", " ").title()

            company_name = company_map.get(
                company_slug, company_slug.replace("-", " ").title()
            )

            # Find location from surrounding HTML context
            job_url = f"{BASE_URL}{full_path}"
            idx = html.find(full_path)
            context = html[max(0, idx - 200) : idx + 500] if idx >= 0 else ""
            loc_match = _RE_LOCATION.search(context)
            job_location = loc_match.group(1).strip() if loc_match else "Remote"

            # Location filter
            if not location_matches(job_location, location_filter):
                continue

            try:
                job = JobListing(
                    id=f"rocketship_{hash(full_path) & 0xFFFFFFFF}",
                    title=job_title,
                    company=company_name,
                    location=job_location,
                    url=job_url,
                    source=JobSourceType.OTHER,
                    discovered_at=datetime.now(),
                )
                jobs.append(job)
            except Exception as e:
                logger.debug("Skipping malformed RemoteRocketship entry: %s", e)

        return jobs
