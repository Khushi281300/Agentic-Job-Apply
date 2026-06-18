"""Job scheduler — runs pipeline searches on a configurable schedule.

Uses asyncio-based scheduling (no external dependency like APScheduler)
to periodically trigger pipeline runs.

Usage:
    scheduler = PipelineScheduler(orchestrator=orch, interval_minutes=60)
    await scheduler.start()   # non-blocking, runs in background
    await scheduler.stop()
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ScheduledTask:
    """A single repeating task with interval and state tracking."""

    def __init__(self, name: str, coro_factory: Callable[[], Awaitable[Any]],
                 interval_secs: float):
        self.name = name
        self._coro_factory = coro_factory
        self.interval_secs = interval_secs
        self.last_run: datetime | None = None
        self.last_error: str = ""
        self.run_count: int = 0
        self.error_count: int = 0
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        """Internal loop that runs the task repeatedly."""
        while True:
            try:
                await self._coro_factory()
                self.last_run = datetime.now()
                self.run_count += 1
                self.last_error = ""
                logger.info("Scheduled[%s]: completed (run #%d)", self.name, self.run_count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                logger.error("Scheduled[%s]: failed: %s", self.name, e)

            await asyncio.sleep(self.interval_secs)

    def start(self) -> None:
        """Start the repeating task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduled[%s]: started (every %.0fs)", self.name, self.interval_secs)

    def stop(self) -> None:
        """Stop the repeating task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduled[%s]: stopped", self.name)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "name": self.name,
            "running": self.is_running,
            "interval_secs": self.interval_secs,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_error": self.last_error or None,
        }


class PipelineScheduler:
    """Manages scheduled pipeline operations.

    Supports multiple scheduled tasks:
    - Job search (frequent)
    - Follow-up checks (daily)
    - Health monitoring (periodic)
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}

    def add_task(self, name: str, coro_factory: Callable[[], Awaitable[Any]],
                 interval_minutes: float) -> None:
        """Register a new scheduled task."""
        self._tasks[name] = ScheduledTask(
            name=name,
            coro_factory=coro_factory,
            interval_secs=interval_minutes * 60,
        )

    async def start(self) -> None:
        """Start all registered tasks."""
        for task in self._tasks.values():
            task.start()
        logger.info("Scheduler started with %d tasks", len(self._tasks))

    async def stop(self) -> None:
        """Stop all tasks gracefully."""
        for task in self._tasks.values():
            task.stop()
        logger.info("Scheduler stopped")

    def status(self) -> dict[str, dict]:
        """Get status of all scheduled tasks."""
        return {name: task.status() for name, task in self._tasks.items()}

    @property
    def is_running(self) -> bool:
        return any(t.is_running for t in self._tasks.values())
