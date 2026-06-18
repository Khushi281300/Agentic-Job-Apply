"""Reusable decorators for the contracts / services layer.

Provides common patterns as decorators to avoid boilerplate.
"""

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def catch_and_log(
    operation: str = "",
    *,
    return_on_error: Any = None,
    log: logging.Logger | None = None,
) -> Callable:
    """Decorator: wraps an async method with try/except, logs errors, returns a default.

    Args:
        operation: Human-readable operation name for log messages.
                   Defaults to the function name.
        return_on_error: Value to return when an exception is caught.
        log: Logger instance. Falls back to module-level logger.

    Usage:
        @catch_and_log("search", return_on_error=[])
        async def search(self, title, location, **kwargs):
            ...  # no try/except needed
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            _log = log or logger
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Try to get source name from self.name if available
                source = ""
                if args and hasattr(args[0], "name"):
                    source = f"{args[0].name} "
                _log.error("%s%s failed: %s", source, op_name, e)
                return return_on_error
        return wrapper
    return decorator
