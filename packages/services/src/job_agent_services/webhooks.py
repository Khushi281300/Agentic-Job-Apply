"""Webhook dispatcher — triggers external integrations on pipeline events.

Sends HTTP POST to configured webhook URLs when events occur
(new match, application sent, outcome recorded, etc.).
Compatible with Zapier, n8n, Make, or any webhook receiver.

Usage:
    webhooks = WebhookDispatcher(urls=["https://hooks.zapier.com/..."])
    await webhooks.dispatch("job.matched", {"job_id": "x", "score": 0.92})
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatches pipeline events to external webhook URLs.

    Features:
    - Non-blocking (fire-and-forget with optional await)
    - Automatic retry on transient failures (1 retry)
    - Event filtering per URL (optional)
    - Timeout protection (5s per request)
    """

    TIMEOUT_SECS = 5.0
    MAX_RETRIES = 1

    def __init__(self, urls: list[str] | None = None,
                 event_filter: dict[str, list[str]] | None = None):
        """
        Args:
            urls: List of webhook URLs to send events to.
            event_filter: Optional {url: [event_types]} to filter which
                         events go to which URLs. If None, all events go everywhere.
        """
        self._urls = urls or []
        self._event_filter = event_filter or {}
        self._client: httpx.AsyncClient | None = None
        self._dispatch_count = 0
        self._error_count = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.TIMEOUT_SECS)
        return self._client

    @property
    def is_configured(self) -> bool:
        return len(self._urls) > 0

    async def dispatch(self, event_type: str, data: dict[str, Any]) -> None:
        """Send an event to all applicable webhook URLs.

        Non-blocking — errors are logged but don't propagate.
        """
        if not self._urls:
            return

        payload = {
            "event": event_type,
            "timestamp": time.time(),
            "data": data,
        }

        tasks = []
        for url in self._urls:
            # Check event filter
            if url in self._event_filter:
                if event_type not in self._event_filter[url]:
                    continue
            tasks.append(self._send(url, payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send(self, url: str, payload: dict) -> None:
        """Send payload to a single URL with retry."""
        client = await self._get_client()

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await client.post(url, json=payload)
                if response.status_code < 400:
                    self._dispatch_count += 1
                    return
                logger.warning(
                    "Webhook %s returned %d", url[:50], response.status_code
                )
            except Exception as e:
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(1.0)
                    continue
                self._error_count += 1
                logger.error("Webhook failed: %s → %s", url[:50], e)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def stats(self) -> dict[str, Any]:
        """Get dispatch statistics."""
        return {
            "configured_urls": len(self._urls),
            "total_dispatched": self._dispatch_count,
            "total_errors": self._error_count,
        }
