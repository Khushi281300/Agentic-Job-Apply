"""Retry utility with exponential backoff and jitter.

Provides both a decorator and an async context manager for retrying
operations that may transiently fail (network calls, LLM requests).

Usage:
    # As a decorator
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_data():
        ...

    # As a function wrapper
    result = await retry_with_backoff(fetch_data, max_retries=3)
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay_secs: float = 1.0
    max_delay_secs: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + optional jitter."""
        delay = min(
            self.base_delay_secs * (self.exponential_base ** attempt),
            self.max_delay_secs,
        )
        if self.jitter:
            delay *= 0.5 + random.random()  # noqa: S311
        return delay


def retry_with_backoff(
    func: Callable | None = None,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator/wrapper for async functions with exponential backoff.

    Can be used as:
        @retry_with_backoff(max_retries=3)
        async def my_func(): ...

    Or directly:
        result = await retry_with_backoff(my_func, max_retries=3)()
    """
    policy = RetryPolicy(
        max_retries=max_retries,
        base_delay_secs=base_delay,
        max_delay_secs=max_delay,
        retryable_exceptions=retryable,
    )

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(policy.max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except policy.retryable_exceptions as e:
                    last_exception = e
                    if attempt < policy.max_retries:
                        delay = policy.delay_for_attempt(attempt)
                        logger.warning(
                            "Retry %d/%d for %s after error: %s (waiting %.1fs)",
                            attempt + 1, policy.max_retries, fn.__name__, e, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            policy.max_retries, fn.__name__, e,
                        )

            raise last_exception  # type: ignore[misc]

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
