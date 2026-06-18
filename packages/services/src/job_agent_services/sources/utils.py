"""Shared utilities for job source scrapers.

Eliminates duplicated timing, rate limiting, and filtering logic.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from job_agent_services.resilience import circuit_registry, CircuitOpenError
from job_agent_services.sources.rate_limiter import source_rate_limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def rate_limited_request(source_name: str) -> AsyncGenerator[None, None]:
    """Acquire rate limiter slot, enforce circuit breaker, measure latency.

    Combines three concerns in one reusable context manager:
    1. Circuit breaker — skips request if source is failing repeatedly
    2. Rate limiting — waits for available slot
    3. Telemetry — records latency on success, error on failure

    Usage:
        async with rate_limited_request("remoteok"):
            response = await http_client.get_json(url)
    """
    breaker = circuit_registry.get(source_name)

    if not breaker.is_available:
        raise CircuitOpenError(source_name, breaker._config.recovery_timeout_secs)

    await source_rate_limiter.acquire(source_name)
    t0 = time.time()
    try:
        yield
        elapsed_ms = (time.time() - t0) * 1000
        source_rate_limiter.record_success(source_name, elapsed_ms)
        breaker.record_success()
    except Exception:
        elapsed_ms = (time.time() - t0) * 1000
        source_rate_limiter.record_error(source_name, f"Failed after {elapsed_ms:.0f}ms")
        breaker.record_failure()
        raise


def location_matches(job_location: str, filter_location: str) -> bool:
    """Check if a job's location passes the user's location filter.

    Returns True (include this job) when:
      - filter is "remote" or empty (accept all)
      - filter string is found within the job's location (case-insensitive)
    """
    if not filter_location or filter_location.lower() in ("remote", ""):
        return True
    return filter_location.lower() in (job_location or "").lower()
