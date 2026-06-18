"""Retry with exponential backoff - production resilience for agent calls.

Provides async retry utility with:
- Configurable retry count
- Exponential backoff with jitter
- Error classification (retryable vs. permanent)
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


# Pre-defined configs for different scenarios
RETRY_LLM = RetryConfig(max_retries=2, base_delay=2.0, max_delay=15.0)
RETRY_BROWSER = RetryConfig(max_retries=1, base_delay=3.0, max_delay=10.0)
RETRY_NETWORK = RetryConfig(max_retries=3, base_delay=1.0, max_delay=30.0)
RETRY_EMAIL = RetryConfig(max_retries=2, base_delay=5.0, max_delay=60.0)


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for the given attempt with exponential backoff + jitter."""
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)
    if config.jitter:
        delay *= (0.5 + random.random())
    return delay


def is_retryable(error: Exception, config: RetryConfig) -> bool:
    """Determine if an error is retryable."""
    return isinstance(error, config.retryable_exceptions)


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig = RETRY_LLM,
    operation_name: str = "",
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry and exponential backoff.

    Args:
        func: The async function to execute
        config: Retry configuration
        operation_name: Name for logging

    Returns:
        The function's return value

    Raises:
        The last exception if all retries are exhausted
    """
    name = operation_name or func.__name__
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            is_last = attempt >= config.max_retries
            retryable = is_retryable(e, config)

            if is_last or not retryable:
                logger.error(
                    "%s failed (attempt %d/%d, %s): %s",
                    name, attempt + 1, config.max_retries + 1,
                    "permanent" if not retryable else "retries exhausted",
                    e,
                )
                raise

            delay = calculate_delay(attempt, config)
            logger.warning(
                "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                name, attempt + 1, config.max_retries + 1, delay, e,
            )
            await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


def with_retry(config: RetryConfig = RETRY_LLM, name: str = ""):
    """Decorator: wrap an async function with retry logic."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(
                func, *args, config=config, operation_name=name or func.__name__, **kwargs
            )
        return wrapper

    return decorator
