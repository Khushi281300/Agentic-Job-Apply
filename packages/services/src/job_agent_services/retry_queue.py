"""Retry queue — persists failed operations for later retry with backoff.

Failed applications go into this queue and are automatically retried
with exponential backoff. Persisted to SQLite so retries survive restarts.

Usage:
    queue = RetryQueue(db_path="data/retry_queue.db")
    await queue.initialize()
    await queue.enqueue("apply", {"job_id": "xyz", "method": "email"})
    pending = await queue.get_pending()
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class _Base(DeclarativeBase):
    pass


class RetryRecord(_Base):
    __tablename__ = "retry_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String, nullable=False)       # e.g. "apply", "email", "fetch"
    payload = Column(Text, nullable=False)            # JSON-serialized task data
    status = Column(String, default="pending")        # pending, in_progress, completed, dead
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    last_error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    next_retry_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class RetryQueue:
    """Persistent retry queue with exponential backoff.

    Items are retried with increasing delays:
    Attempt 1: immediate, 2: 5min, 3: 30min, 4: 2hr, 5: 12hr
    After max_attempts, items are marked 'dead' for manual review.
    """

    BASE_DELAY_MINUTES = 5.0
    BACKOFF_MULTIPLIER = 3.0

    def __init__(self, db_path: str = "data/retry_queue.db"):
        from pathlib import Path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if needed."""
        if not self._initialized:
            async with self._engine.begin() as conn:
                await conn.run_sync(_Base.metadata.create_all)
            self._initialized = True

    async def enqueue(self, task_type: str, payload: dict[str, Any],
                      max_attempts: int = 5) -> int:
        """Add a task to the retry queue. Returns the record ID."""
        await self.initialize()
        async with self._session_factory() as session:
            record = RetryRecord(
                task_type=task_type,
                payload=json.dumps(payload),
                max_attempts=max_attempts,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            logger.info("Retry queue: enqueued %s task (id=%d)", task_type, record.id)
            return record.id

    async def get_pending(self) -> list[dict[str, Any]]:
        """Get all tasks ready to be retried (next_retry_at <= now)."""
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(RetryRecord)
                .where(RetryRecord.status == "pending")
                .where(RetryRecord.next_retry_at <= datetime.now())
                .order_by(RetryRecord.next_retry_at)
            )
            records = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "task_type": r.task_type,
                    "payload": json.loads(r.payload),
                    "attempts": r.attempts,
                    "max_attempts": r.max_attempts,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in records
            ]

    async def mark_success(self, record_id: int) -> None:
        """Mark a task as successfully completed."""
        await self.initialize()
        async with self._session_factory() as session:
            record = await session.get(RetryRecord, record_id)
            if record:
                record.status = "completed"
                record.completed_at = datetime.now()
                await session.commit()

    async def mark_failed(self, record_id: int, error: str) -> None:
        """Record a failure and schedule the next retry (or mark dead)."""
        await self.initialize()
        async with self._session_factory() as session:
            record = await session.get(RetryRecord, record_id)
            if not record:
                return

            record.attempts += 1
            record.last_error = error

            if record.attempts >= record.max_attempts:
                record.status = "dead"
                logger.warning(
                    "Retry queue: task %d exhausted %d attempts, marked dead",
                    record_id, record.max_attempts,
                )
            else:
                # Exponential backoff
                delay_minutes = (
                    self.BASE_DELAY_MINUTES * (self.BACKOFF_MULTIPLIER ** (record.attempts - 1))
                )
                record.next_retry_at = datetime.now() + timedelta(minutes=delay_minutes)
                logger.info(
                    "Retry queue: task %d attempt %d failed, next retry in %.0f min",
                    record_id, record.attempts, delay_minutes,
                )

            await session.commit()

    async def get_stats(self) -> dict[str, int]:
        """Get queue statistics."""
        await self.initialize()
        async with self._session_factory() as session:
            from sqlalchemy import func
            result = await session.execute(
                select(RetryRecord.status, func.count()).group_by(RetryRecord.status)
            )
            counts = dict(result.all())
            return {
                "pending": counts.get("pending", 0),
                "in_progress": counts.get("in_progress", 0),
                "completed": counts.get("completed", 0),
                "dead": counts.get("dead", 0),
            }

    async def get_dead_letters(self) -> list[dict[str, Any]]:
        """Get tasks that have exhausted all retries (for manual review)."""
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(RetryRecord).where(RetryRecord.status == "dead")
            )
            records = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "task_type": r.task_type,
                    "payload": json.loads(r.payload),
                    "attempts": r.attempts,
                    "last_error": r.last_error,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in records
            ]
