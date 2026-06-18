"""Resilience utilities - circuit breaker and rate limiting."""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker pattern - stops calling a failing service.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Service is down, requests fail immediately
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = "closed"
        self._last_failure_time = 0.0

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "open"
            logger.warning("Circuit breaker OPEN after %d failures", self._failures)

    @property
    def is_open(self) -> bool:
        return self.state == "open"


class RateLimiter:
    """Per-domain rate limiter with token bucket algorithm."""

    def __init__(self, requests_per_minute: int = 10):
        self.rpm = requests_per_minute
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    async def acquire(self, domain: str) -> None:
        """Wait until a request is allowed for this domain."""
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
        """Get remaining requests for this domain in current window."""
        now = time.time()
        recent = [t for t in self._timestamps[domain] if now - t < 60.0]
        return max(0, self.rpm - len(recent))


# Global rate limiter
rate_limiter = RateLimiter(requests_per_minute=10)
