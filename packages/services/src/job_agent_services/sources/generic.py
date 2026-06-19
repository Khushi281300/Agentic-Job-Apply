"""Generic YAML-driven job sources — API JSON, HTML scrape, Browser scrape, and RSS.

These classes are instantiated dynamically from config/job_sources.yaml.
No per-source Python files needed — just add a YAML entry and restart.
"""

import logging
import re
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from job_agent_contracts.models import JobListing, JobSourceType
from job_agent_services.http.client import http_client
from job_agent_services.sources.base_source import BaseJobSource
from job_agent_services.sources.utils import rate_limited_request, location_matches

logger = logging.getLogger(__name__)


class ApiJsonSource(BaseJobSource):
    """Generic job source backed by a JSON API.

    Config fields used:
        name, base_url, search_url, headers, json_mapping, skip_first
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config["name"]
        self._search_url = config["search_url"]
        self._headers = config.get("headers", {})
        self._mapping = config.get("json_mapping", {})
        self._skip_first = config.get("skip_first", False)

    @property
    def name(self) -> str:
        return self._name

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        url = self._build_url(self._search_url, title, location)

        async with rate_limited_request(self._name):
            response = await http_client.get_json(url, headers=self._headers)

        items = self._extract_items(response)
        jobs = self._parse_items(items, lambda item: self._parse_one(item, location))
        logger.info("%s: found %d jobs for '%s'", self._name, len(jobs), title)
        return jobs

    async def _do_fetch_details(self, url: str) -> str:
        html = await http_client.get(url, headers=self._headers)
        return html[:5000] if html else ""

    def _extract_items(self, response: Any) -> list:
        """Pull the job list from the API response."""
        if isinstance(response, list):
            return response[1:] if self._skip_first else response
        if isinstance(response, dict):
            # Try common keys: jobs, results, data, listings
            for key in ("jobs", "results", "data", "listings", "items"):
                if key in response and isinstance(response[key], list):
                    return response[key]
            return []
        return []

    def _parse_one(self, item: Any, location: str) -> JobListing | None:
        if not isinstance(item, dict):
            return None

        m = self._mapping
        id_val = _deep_get(item, m.get("id_field", "id"))
        if not id_val:
            return None

        prefix = m.get("id_prefix", f"{self._name}_")
        loc = _deep_get(item, m.get("location", "location")) or "Remote"

        if not location_matches(loc, location):
            return None

        title = _deep_get(item, m.get("title", "title")) or "Unknown"
        company = _deep_get(item, m.get("company", "company")) or "Unknown"

        return JobListing(
            id=f"{prefix}{id_val}",
            title=title,
            company=company,
            location=loc,
            url=_deep_get(item, m.get("url", "url")) or "",
            source=JobSourceType.OTHER,
            description=_deep_get(item, m.get("description", "description")) or "",
            salary_min=_parse_salary(_deep_get(item, m.get("salary", "salary_min"))),
            salary_max=_parse_salary(_deep_get(item, m.get("salary_max", "salary_max"))),
            tags=_deep_get(item, m.get("tags", "tags")) or [],
            discovered_at=datetime.now(),
        )

    @staticmethod
    def _build_url(template: str, title: str, location: str) -> str:
        return template.format(
            title=title.replace(" ", "+"),
            location=location.replace(" ", "+"),
        )


class HtmlScrapeSource(BaseJobSource):
    """Generic job source that scrapes HTML pages using CSS selectors.

    Config fields used:
        name, base_url, search_url, headers, selectors
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config["name"]
        self._base_url = config["base_url"].rstrip("/")
        self._search_url = config["search_url"]
        self._headers = config.get("headers", {})
        self._selectors = config.get("selectors", {})

    @property
    def name(self) -> str:
        return self._name

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        url = _build_url(self._search_url, title, location)

        async with rate_limited_request(self._name):
            html = await http_client.get(url, headers=self._headers)

        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        card_sel = self._selectors.get("job_card", ".job-card")
        cards = soup.select(card_sel)

        jobs = self._parse_items(cards, lambda card: self._parse_card(card, location))
        logger.info("%s: found %d jobs for '%s'", self._name, len(jobs), title)
        return jobs

    async def _do_fetch_details(self, url: str) -> str:
        async with rate_limited_request(self._name):
            html = await http_client.get(url, headers=self._headers)

        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")
        desc_sel = self._selectors.get("description", ".job-description")
        desc_el = soup.select_one(desc_sel)
        text = desc_el.get_text(strip=True, separator="\n") if desc_el else ""
        return text[:5000]

    def _parse_card(self, card: Any, location: str) -> JobListing | None:
        s = self._selectors

        title_el = card.select_one(s.get("title", ".job-title"))
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            return None

        company_el = card.select_one(s.get("company", ".company"))
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        loc_el = card.select_one(s.get("location", ".location"))
        loc = loc_el.get_text(strip=True) if loc_el else "Remote"

        if not location_matches(loc, location):
            return None

        # Extract link
        link_el = card.select_one(s.get("link", "a"))
        href = ""
        if link_el:
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"{self._base_url}{href}"

        # Generate ID from href or title+company
        job_id = f"{self._name}_{_slugify(title)}_{_slugify(company)}"

        return JobListing(
            id=job_id,
            title=title,
            company=company,
            location=loc,
            url=href,
            source=JobSourceType.OTHER,
            description="",  # fetched later via fetch_details
            discovered_at=datetime.now(),
        )


class BrowserScrapeSource(BaseJobSource):
    """Generic job source using Playwright for JS-rendered / anti-bot pages.

    Same as HtmlScrapeSource but renders the page in a real browser first.
    Use type: browser_scrape in YAML for sites that block plain HTTP requests
    (e.g., Naukri, Glassdoor, Indeed with bot detection).

    Config fields used:
        name, base_url, search_url, selectors, wait_selector (optional)
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config["name"]
        self._base_url = config["base_url"].rstrip("/")
        self._search_url = config["search_url"]
        self._selectors = config.get("selectors", {})
        self._wait_selector = config.get("wait_selector", "")
        self._browser = None

    @property
    def name(self) -> str:
        return self._name

    async def _get_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            # Use stealth to bypass anti-bot detection
            try:
                from playwright_stealth import Stealth
                stealth = Stealth()
                browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                await stealth.apply_stealth_async(context)
                self._page = await context.new_page()
            except ImportError:
                # Fallback without stealth
                browser = await self._playwright.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                self._page = await context.new_page()
            self._browser_instance = browser
        return self

    async def close(self) -> None:
        if hasattr(self, "_browser_instance") and self._browser_instance:
            await self._browser_instance.close()
            self._browser_instance = None
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._browser = None
        self._page = None

    async def _navigate(self, url: str) -> str:
        """Navigate and return page content."""
        await self._page.goto(url, wait_until="networkidle", timeout=30000)
        return await self._page.content()

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        url = _build_url(self._search_url, title, location)

        async with rate_limited_request(self._name):
            await self._get_browser()
            html = await self._navigate(url)
            # Optionally wait for a specific element to appear
            if self._wait_selector and self._page:
                try:
                    await self._page.wait_for_selector(self._wait_selector, timeout=10000)
                    html = await self._page.content()
                except Exception:
                    pass  # Proceed anyway with whatever loaded

        if not html:
            logger.warning("%s: empty/blocked browser response", self._name)
            return []

        soup = BeautifulSoup(html, "html.parser")
        card_sel = self._selectors.get("job_card", ".job-card")
        cards = soup.select(card_sel)

        jobs = self._parse_items(cards, lambda card: self._parse_card(card, location))
        logger.info("%s: found %d jobs for '%s' (browser)", self._name, len(jobs), title)
        return jobs

    async def _do_fetch_details(self, url: str) -> str:
        async with rate_limited_request(self._name):
            await self._get_browser()
            html = await self._navigate(url)

        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")
        desc_sel = self._selectors.get("description", ".job-description")
        desc_el = soup.select_one(desc_sel)
        text = desc_el.get_text(strip=True, separator="\n") if desc_el else ""
        return text[:5000]

    def _parse_card(self, card: Any, location: str) -> JobListing | None:
        s = self._selectors

        title_el = card.select_one(s.get("title", ".job-title"))
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            return None

        company_el = card.select_one(s.get("company", ".company"))
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        loc_el = card.select_one(s.get("location", ".location"))
        loc = loc_el.get_text(strip=True) if loc_el else "Remote"

        if not location_matches(loc, location):
            return None

        link_el = card.select_one(s.get("link", "a"))
        href = ""
        if link_el:
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"{self._base_url}{href}"

        job_id = f"{self._name}_{_slugify(title)}_{_slugify(company)}"

        return JobListing(
            id=job_id,
            title=title,
            company=company,
            location=loc,
            url=href,
            source=JobSourceType.OTHER,
            description="",
            discovered_at=datetime.now(),
        )

    async def search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        """Override base to reset browser on error."""
        try:
            return await self._do_search(title, location, **kwargs)
        except Exception as e:
            logger.error("%s browser search failed: %s", self._name, e)
            await self.close()
            return []


class RssSource(BaseJobSource):
    """Generic job source that reads RSS/Atom feeds.

    Config fields used:
        name, base_url, search_url, headers, categories, rss_mapping
    """

    def __init__(self, config: dict):
        self._config = config
        self._name = config["name"]
        self._base_url = config["base_url"].rstrip("/")
        self._search_url = config["search_url"]
        self._headers = config.get("headers", {})
        self._categories = config.get("categories", [])
        self._mapping = config.get("rss_mapping", {})

    @property
    def name(self) -> str:
        return self._name

    async def _do_search(self, title: str, location: str, **kwargs: Any) -> list[JobListing]:
        all_jobs: list[JobListing] = []

        # If categories are defined, fetch each category feed
        urls = []
        if self._categories:
            for cat in self._categories:
                urls.append(
                    self._search_url.format(
                        title=title.replace(" ", "-"),
                        location=location.replace(" ", "-"),
                        category=cat,
                    )
                )
        else:
            urls.append(_build_url(self._search_url, title, location))

        for url in urls:
            async with rate_limited_request(self._name):
                xml_text = await http_client.get(url, headers=self._headers)

            if not xml_text:
                continue

            try:
                root = ElementTree.fromstring(xml_text)
            except ElementTree.ParseError:
                logger.warning("%s: failed to parse RSS from %s", self._name, url)
                continue

            # Support both RSS 2.0 (<item>) and Atom (<entry>)
            items = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

            jobs = self._parse_items(items, lambda el: self._parse_entry(el, title, location))
            all_jobs.extend(jobs)

        logger.info("%s: found %d jobs for '%s'", self._name, len(all_jobs), title)
        return all_jobs

    async def _do_fetch_details(self, url: str) -> str:
        html = await http_client.get(url, headers=self._headers)
        return html[:5000] if html else ""

    def _parse_entry(self, el: ElementTree.Element, title_filter: str, location: str) -> JobListing | None:
        m = self._mapping

        def _text(tag: str) -> str:
            # Try plain tag first, then with Atom namespace
            node = el.find(tag)
            if node is None:
                node = el.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
            return (node.text or "").strip() if node is not None else ""

        item_title = _text(m.get("title", "title"))
        if not item_title:
            return None

        # Basic relevance check — title keyword should appear somewhere
        if title_filter.lower() not in item_title.lower():
            return None

        company = _text(m.get("company", "company")) or "Unknown"
        link = _text(m.get("url", "link"))
        if not link:
            link_el = el.find("link")
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")

        if link and not link.startswith("http"):
            link = f"{self._base_url}{link}"

        desc = _text(m.get("description", "description"))
        guid = _text(m.get("id_field", "guid")) or _slugify(item_title)
        prefix = m.get("id_prefix", f"{self._name}_")

        return JobListing(
            id=f"{prefix}{guid}",
            title=item_title,
            company=company,
            location="Remote",
            url=link,
            source=JobSourceType.OTHER,
            description=desc[:2000],
            discovered_at=datetime.now(),
        )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_url(template: str, title: str, location: str) -> str:
    return template.format(
        title=title.replace(" ", "+"),
        location=location.replace(" ", "+"),
    )


def _deep_get(obj: dict, key: str) -> Any:
    """Get a value from a nested dict using dot notation (e.g. 'company.display_name')."""
    if not key or not isinstance(obj, dict):
        return None
    parts = key.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _parse_salary(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(str(value).replace(",", "").replace("$", "").replace("£", "").replace("€", "").strip())
    except (ValueError, TypeError):
        return 0


def _slugify(text: str) -> str:
    """Make a URL-safe slug from text."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip())[:60]
