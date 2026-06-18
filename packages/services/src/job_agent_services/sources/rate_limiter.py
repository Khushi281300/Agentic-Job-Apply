"""Per-source rate limiter — prevents hammering job boards.

Each source gets its own configurable request budget per time window.
Used by scrapers before making requests.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default limits per source (requests per window)
_DEFAULT_LIMITS: dict[str, tuple[int, float]] = {
    "remoteok":        (10, 60.0),   # 10 req/min
    "remotive":        (10, 60.0),
    "remoterocketship": (5, 60.0),   # browser scraping — go slower
}

_DEFAULT_MAX = 15
_DEFAULT_WINDOW = 60.0


@dataclass
class _Bucket:
    max_requests: int
    window_secs: float
    timestamps: list[float] = field(default_factory=list)
    total_requests: int = 0
    total_blocked: int = 0
    last_error: str = ""
    last_error_at: float = 0.0
    last_success_at: float = 0.0
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def prune(self, now: float) -> None:
        cutoff = now - self.window_secs
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def allowed(self) -> bool:
        now = time.time()
        self.prune(now)
        if len(self.timestamps) >= self.max_requests:
            self.total_blocked += 1
            return False
        self.timestamps.append(now)
        self.total_requests += 1
        return True

    def record_success(self, latency_ms: float) -> None:
        self.last_success_at = time.time()
        self._latencies.append(latency_ms)
        if len(self._latencies) > 50:
            self._latencies = self._latencies[-50:]
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_error(self, error: str) -> None:
        self.last_error = error
        self.last_error_at = time.time()

    def wait_seconds(self) -> float:
        """How long until the next slot opens, or 0 if a slot is available."""
        now = time.time()
        self.prune(now)
        if len(self.timestamps) < self.max_requests:
            return 0.0
        return self.timestamps[0] + self.window_secs - now

    def health(self) -> dict:
        now = time.time()
        self.prune(now)
        return {
            "current_usage": len(self.timestamps),
            "max_requests": self.max_requests,
            "window_secs": self.window_secs,
            "total_requests": self.total_requests,
            "total_blocked": self.total_blocked,
            "last_success_ago_secs": round(now - self.last_success_at, 1) if self.last_success_at else None,
            "last_error": self.last_error or None,
            "last_error_ago_secs": round(now - self.last_error_at, 1) if self.last_error_at else None,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


class SourceRateLimiter:
    """Manages per-source rate limiting with health tracking."""

    def __init__(self, limits: dict[str, tuple[int, float]] | None = None):
        self._limits = limits or _DEFAULT_LIMITS
        self._buckets: dict[str, _Bucket] = {}

    def _get_bucket(self, source: str) -> _Bucket:
        if source not in self._buckets:
            max_req, window = self._limits.get(source, (_DEFAULT_MAX, _DEFAULT_WINDOW))
            self._buckets[source] = _Bucket(max_requests=max_req, window_secs=window)
        return self._buckets[source]

    async def acquire(self, source: str) -> bool:
        """Wait until a request slot is available for this source. Returns True."""
        bucket = self._get_bucket(source)
        wait = bucket.wait_seconds()
        if wait > 0:
            logger.debug("Rate limiter: %s waiting %.1fs", source, wait)
            await asyncio.sleep(wait)
        return bucket.allowed()

    def try_acquire(self, source: str) -> bool:
        """Non-blocking: returns False if rate limited."""
        return self._get_bucket(source).allowed()

    def record_success(self, source: str, latency_ms: float) -> None:
        self._get_bucket(source).record_success(latency_ms)

    def record_error(self, source: str, error: str) -> None:
        self._get_bucket(source).record_error(error)

    def health(self) -> dict[str, dict]:
        """Get health status for all tracked sources."""
        return {name: bucket.health() for name, bucket in self._buckets.items()}

    def source_health(self, source: str) -> dict:
        return self._get_bucket(source).health()


# Module-level singleton
source_rate_limiter = SourceRateLimiter()
