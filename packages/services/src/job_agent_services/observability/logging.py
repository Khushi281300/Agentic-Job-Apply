"""Structured logging configuration.

Provides a unified logging setup that outputs JSON in production
and human-readable format in development. Uses stdlib logging with
a custom JSON formatter (no external dependency on structlog).

Usage:
    from job_agent_services.observability.logging import setup_logging

    setup_logging(level="INFO", json_output=True)
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Produces one JSON object per log line — structured for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Include extra fields added via `logger.info("msg", extra={...})`
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated", "thread",
            "threadName", "msecs", "pathname", "filename", "module", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "levelno", "levelname",
            "message", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Colored, human-readable formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        prefix = f"{color}{ts} [{record.levelname:<7}]{self.RESET}"
        name = f"\033[90m{record.name}\033[0m"
        msg = record.getMessage()

        line = f"{prefix} {name}: {msg}"

        if record.exc_info and record.exc_info[0]:
            line += "\n" + self.formatException(record.exc_info)

        return line


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    module_levels: dict[str, str] | None = None,
) -> None:
    """Configure logging for the entire application.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, output structured JSON. If False, human-readable.
        module_levels: Per-module level overrides, e.g. {"httpx": "WARNING"}.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter() if json_output else HumanFormatter())
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    noisy_loggers = ["httpx", "httpcore", "chromadb", "urllib3", "asyncio"]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Apply custom module levels
    if module_levels:
        for module, mod_level in module_levels.items():
            logging.getLogger(module).setLevel(getattr(logging, mod_level.upper()))
