"""HTTP client service - shared, configurable HTTP client with retry logic."""

import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Common browser User-Agent strings — rotated per client session
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
]


class HttpClient:
    """Reusable async HTTP client with rotating user agents and retry."""

    def __init__(self, timeout: int = 30, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._cached_ua: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HttpClient":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
            self._cached_ua = random.choice(_USER_AGENTS)
        return self._client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._cached_ua or random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def _request(
        self, method: str, url: str, headers: dict | None = None,
        params: dict | None = None, json_data: dict | None = None,
        expect_json: bool = False,
    ) -> Any:
        """Unified request method with retries."""
        merged_headers = {**self._headers, **(headers or {})}
        if expect_json:
            merged_headers["Accept"] = "application/json"
        client = await self._get_client()

        for attempt in range(self.max_retries + 1):
            try:
                if method == "POST":
                    response = await client.post(url, json=json_data, headers=merged_headers)
                else:
                    response = await client.get(url, headers=merged_headers, params=params)

                if response.status_code == 200:
                    return response.json() if expect_json else response.text
                logger.warning("HTTP %d for %s (attempt %d)", response.status_code, url, attempt + 1)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("Request failed for %s (attempt %d): %s", url, attempt + 1, e)

        return {} if expect_json else ""

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None) -> str:
        """GET request with retries. Returns response text."""
        return await self._request("GET", url, headers=headers, params=params)

    async def get_json(self, url: str, headers: dict | None = None, params: dict | None = None) -> Any:
        """GET request expecting JSON response."""
        return await self._request("GET", url, headers=headers, params=params, expect_json=True)

    async def post_json(self, url: str, data: dict[str, Any], headers: dict | None = None) -> dict[str, Any] | None:
        """POST JSON data with retries."""
        result = await self._request("POST", url, headers=headers, json_data=data, expect_json=True)
        return result if result else None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self._cached_ua = None


# Shared client instance
http_client = HttpClient()
