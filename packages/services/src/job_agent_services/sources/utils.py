"""Shared utilities for job source scrapers.

Eliminates duplicated timing, rate limiting, and filtering logic.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from job_agent_services.sources.rate_limiter import source_rate_limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def rate_limited_request(source_name: str) -> AsyncGenerator[None, None]:
    """Acquire rate limiter slot, measure latency, record success/error.

    Usage:
        async with rate_limited_request("remoteok"):
            response = await http_client.get_json(url)
    """
    await source_rate_limiter.acquire(source_name)
    t0 = time.time()
    try:
        yield
        source_rate_limiter.record_success(source_name, (time.time() - t0) * 1000)
    except Exception:
        source_rate_limiter.record_error(source_name, f"Request failed after {(time.time() - t0)*1000:.0f}ms")
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
