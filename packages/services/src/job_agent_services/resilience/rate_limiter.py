"""Simple per-domain rate limiter with token bucket algorithm.

For job source-specific rate limiting with health tracking,
use `job_agent_services.sources.rate_limiter.SourceRateLimiter` instead.
"""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """Per-domain rate limiter — limits requests to N per minute per domain."""

    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    async def acquire(self, domain: str) -> None:
        """Wait until a request slot is available for this domain."""
        now = time.time()
        window = 60.0

        self._timestamps[domain] = [
            t for t in self._timestamps[domain] if now - t < window
        ]

        while len(self._timestamps[domain]) >= self.rpm:
            oldest = self._timestamps[domain][0]
            wait_time = window - (now - oldest) + 0.1
            logger.debug("Rate limited on %s, waiting %.1fs", domain, wait_time)
            await asyncio.sleep(wait_time)
            now = time.time()
            self._timestamps[domain] = [
                t for t in self._timestamps[domain] if now - t < window
            ]

        self._timestamps[domain].append(now)

    def get_remaining(self, domain: str) -> int:
        """Get remaining request budget in current window."""
        now = time.time()
        recent = [t for t in self._timestamps[domain] if now - t < 60.0]
        return max(0, self.rpm - len(recent))


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=10)
