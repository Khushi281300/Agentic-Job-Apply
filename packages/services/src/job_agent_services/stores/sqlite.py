"""Database service - async SQLite persistence for application tracking."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Float, Index, String, Text, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from job_agent_contracts.models import JobListing, JobStatus, MatchResult

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String)
    description = Column(Text)
    url = Column(String, unique=True)
    source = Column(String)
    status = Column(String, default=JobStatus.DISCOVERED.value)
    match_score = Column(Float, default=0.0)
    match_data = Column(Text, default="{}")
    tailored_data = Column(Text, default="{}")
    discovered_at = Column(DateTime, default=datetime.now)
    applied_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    error = Column(Text, default="")
    raw_data = Column(Text, default="{}")
    # Outcome tracking (for adaptive scoring)
    outcome = Column(String, default="")          # callback, interview, offer, rejected, no_response
    outcome_at = Column(DateTime, nullable=True)
    follow_up_at = Column(DateTime, nullable=True)
    # Application deadline tracking
    deadline = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_jobs_url", "url"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_applied_at", "applied_at"),
        Index("ix_jobs_discovered_at", "discovered_at"),
        Index("ix_jobs_status_score", "status", "match_score"),
        Index("ix_jobs_outcome", "outcome"),
        Index("ix_jobs_deadline", "deadline"),
    )


class Database:
    """Async SQLite database for tracking job applications."""

    def __init__(self, db_path: str = "data/applications.db") -> None:
        from pathlib import Path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        if not self._initialized:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._initialized = True

    # ─── Reusable Record Update Helper ───────────────────────────────────────

    async def _update_record(
        self,
        job_id: str,
        updater: Any,
    ) -> bool:
        """Generic record update — loads record, applies updater, commits.

        Args:
            job_id: Primary key of the record.
            updater: Callable that receives the JobRecord and mutates it.

        Returns:
            True if the record existed and was updated, False otherwise.
        """
        await self.initialize()
        async with self._session_factory() as session:
            record = await session.get(JobRecord, job_id)
            if record:
                updater(record)
                await session.commit()
                return True
            return False

    # ─── Public Methods ──────────────────────────────────────────────────────

    async def save_job(self, job: JobListing, status: JobStatus = JobStatus.DISCOVERED) -> None:
        """Save or update a job listing (upsert via merge)."""
        await self.initialize()
        async with self._session_factory() as session:
            record = JobRecord(
                id=job.id,
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description,
                url=job.url,
                source=job.source.value if hasattr(job.source, 'value') else str(job.source),
                status=status.value,
                raw_data=job.model_dump_json(),
            )
            await session.merge(record)
            await session.commit()

    async def update_match(self, job_id: str, match: MatchResult) -> None:
        def _apply(record: JobRecord) -> None:
            record.match_score = match.overall_score
            record.match_data = match.model_dump_json()
            record.status = JobStatus.MATCHED.value
        await self._update_record(job_id, _apply)

    async def update_status(self, job_id: str, status: JobStatus, error: str = "") -> None:
        def _apply(record: JobRecord) -> None:
            record.status = status.value
            if error:
                record.error = error
            if status == JobStatus.APPLIED:
                record.applied_at = datetime.now()
        await self._update_record(job_id, _apply)

    async def update_application_status(self, job_id: str, status: str) -> None:
        """Update application status by string (used by outcome tracker)."""
        await self._update_record(job_id, lambda r: setattr(r, "status", status))

    async def get_application(self, job_id: str) -> dict[str, Any] | None:
        """Get a single application record."""
        await self.initialize()
        async with self._session_factory() as session:
            record = await session.get(JobRecord, job_id)
            if record:
                return {
                    "job_id": record.id,
                    "title": record.title,
                    "company": record.company,
                    "status": record.status,
                    "applied_at": record.applied_at,
                }
            return None

    async def get_pending_applications(self) -> list[dict[str, Any]]:
        """Get applications that are still pending."""
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobRecord).where(JobRecord.status == JobStatus.APPLIED.value)
            )
            records = result.scalars().all()
            return [
                {"job_id": r.id, "title": r.title, "company": r.company,
                 "applied_at": r.applied_at}
                for r in records
            ]

    async def is_already_seen(self, job_url: str) -> bool:
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(JobRecord).where(JobRecord.url == job_url)
            )
            return (result.scalar() or 0) > 0

    async def get_today_application_count(self) -> int:
        await self.initialize()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(JobRecord).where(JobRecord.applied_at >= today)
            )
            return result.scalar() or 0

    async def get_jobs_by_status(self, status: JobStatus) -> list[dict]:
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobRecord).where(JobRecord.status == status.value)
            )
            records = result.scalars().all()
            return [
                {"id": r.id, "title": r.title, "company": r.company,
                 "url": r.url, "score": r.match_score, "status": r.status}
                for r in records
            ]

    async def get_all_jobs_detailed(self) -> list[dict]:
        """Get all jobs with full match/tailored data for results view."""
        await self.initialize()
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobRecord).order_by(JobRecord.discovered_at.desc())
            )
            records = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "company": r.company,
                    "location": r.location or "",
                    "url": r.url,
                    "source": r.source or "",
                    "status": r.status,
                    "match_score": r.match_score,
                    "match_data": r.match_data or "{}",
                    "tailored_data": r.tailored_data or "{}",
                    "discovered_at": r.discovered_at.isoformat() if r.discovered_at else "",
                    "applied_at": r.applied_at.isoformat() if r.applied_at else "",
                    "error": r.error or "",
                }
                for r in records
            ]

    async def get_stats(self) -> dict:
        await self.initialize()
        async with self._session_factory() as session:
            # Single query with GROUP BY instead of 4 separate counts
            result = await session.execute(
                select(JobRecord.status, func.count()).group_by(JobRecord.status)
            )
            counts = dict(result.all())
            return {
                "total_discovered": sum(counts.values()),
                "applied": counts.get(JobStatus.APPLIED.value, 0),
                "matched_pending": counts.get(JobStatus.MATCHED.value, 0),
                "rejected": counts.get(JobStatus.REJECTED.value, 0),
            }

    # ─── Outcome Tracking & Success Analytics ────────────────────────────────

    async def record_outcome(self, job_id: str, outcome: str) -> None:
        """Record application outcome: callback, interview, offer, rejected, no_response."""
        def _apply(record: JobRecord) -> None:
            record.outcome = outcome
            record.outcome_at = datetime.now()
        await self._update_record(job_id, _apply)

    async def set_follow_up(self, job_id: str, follow_up_at: datetime) -> None:
        """Schedule a follow-up reminder for a job."""
        await self._update_record(job_id, lambda r: setattr(r, "follow_up_at", follow_up_at))

    async def get_due_follow_ups(self) -> list[dict]:
        """Get applications due for follow-up."""
        await self.initialize()
        async with self._session_factory() as session:
            now = datetime.now()
            result = await session.execute(
                select(JobRecord)
                .where(JobRecord.follow_up_at <= now)
                .where(JobRecord.outcome == "")
                .where(JobRecord.status == JobStatus.APPLIED.value)
            )
            records = result.scalars().all()
            return [
                {"id": r.id, "title": r.title, "company": r.company,
                 "applied_at": r.applied_at.isoformat() if r.applied_at else "",
                 "follow_up_at": r.follow_up_at.isoformat() if r.follow_up_at else ""}
                for r in records
            ]

    # ─── Deadline Tracking ───────────────────────────────────────────────────

    async def set_deadline(self, job_id: str, deadline: datetime) -> bool:
        """Set an application deadline for a job."""
        return await self._update_record(job_id, lambda r: setattr(r, "deadline", deadline))

    async def get_upcoming_deadlines(self, days: int = 14) -> list[dict]:
        """Get jobs with deadlines in the next N days."""
        await self.initialize()
        async with self._session_factory() as session:
            now = datetime.now()
            cutoff = now + timedelta(days=days)
            result = await session.execute(
                select(JobRecord)
                .where(JobRecord.deadline.isnot(None))
                .where(JobRecord.deadline >= now)
                .where(JobRecord.deadline <= cutoff)
                .where(JobRecord.status.notin_([
                    JobStatus.APPLIED.value, JobStatus.REJECTED.value,
                ]))
                .order_by(JobRecord.deadline.asc())
            )
            records = result.scalars().all()
            return [
                {
                    "id": r.id, "title": r.title, "company": r.company,
                    "status": r.status, "url": r.url,
                    "match_score": r.match_score,
                    "deadline": r.deadline.isoformat() if r.deadline else "",
                    "days_left": (r.deadline - now).days if r.deadline else None,
                }
                for r in records
            ]

    async def get_expired_deadlines(self) -> list[dict]:
        """Get jobs whose deadlines have passed without application."""
        await self.initialize()
        async with self._session_factory() as session:
            now = datetime.now()
            result = await session.execute(
                select(JobRecord)
                .where(JobRecord.deadline.isnot(None))
                .where(JobRecord.deadline < now)
                .where(JobRecord.status.notin_([
                    JobStatus.APPLIED.value, JobStatus.REJECTED.value,
                ]))
                .order_by(JobRecord.deadline.desc())
            )
            records = result.scalars().all()
            return [
                {
                    "id": r.id, "title": r.title, "company": r.company,
                    "status": r.status, "url": r.url,
                    "deadline": r.deadline.isoformat() if r.deadline else "",
                }
                for r in records
            ]

    async def get_success_analytics(self) -> dict:
        """Get application success rates by source, score range, etc."""
        await self.initialize()
        async with self._session_factory() as session:
            # Overall outcome breakdown
            result = await session.execute(
                select(JobRecord.outcome, func.count())
                .where(JobRecord.status == JobStatus.APPLIED.value)
                .group_by(JobRecord.outcome)
            )
            outcome_counts = dict(result.all())

            # Success rate by source
            result = await session.execute(
                select(JobRecord.source, JobRecord.outcome, func.count())
                .where(JobRecord.status == JobStatus.APPLIED.value)
                .group_by(JobRecord.source, JobRecord.outcome)
            )
            by_source: dict[str, dict] = {}
            for source, outcome, count in result.all():
                if source not in by_source:
                    by_source[source] = {"total": 0, "positive": 0}
                by_source[source]["total"] += count
                if outcome in ("callback", "interview", "offer"):
                    by_source[source]["positive"] += count

            # Success rate by match score range
            result = await session.execute(
                select(JobRecord.match_score, JobRecord.outcome)
                .where(JobRecord.status == JobStatus.APPLIED.value)
            )
            by_score: dict[str, dict] = {
                "60-70%": {"total": 0, "positive": 0},
                "70-80%": {"total": 0, "positive": 0},
                "80-90%": {"total": 0, "positive": 0},
                "90-100%": {"total": 0, "positive": 0},
            }
            for score, outcome in result.all():
                if score is None:
                    continue
                if score >= 0.9:
                    bucket = "90-100%"
                elif score >= 0.8:
                    bucket = "80-90%"
                elif score >= 0.7:
                    bucket = "70-80%"
                else:
                    bucket = "60-70%"
                by_score[bucket]["total"] += 1
                if outcome in ("callback", "interview", "offer"):
                    by_score[bucket]["positive"] += 1

            total_applied = sum(outcome_counts.values()) or 1
            positive = sum(c for o, c in outcome_counts.items() if o in ("callback", "interview", "offer"))

            return {
                "total_applied": total_applied,
                "overall_success_rate": round(positive / total_applied, 3),
                "outcomes": outcome_counts,
                "by_source": {
                    s: {**v, "success_rate": round(v["positive"] / max(v["total"], 1), 3)}
                    for s, v in by_source.items()
                },
                "by_score_range": {
                    s: {**v, "success_rate": round(v["positive"] / max(v["total"], 1), 3)}
                    for s, v in by_score.items()
                },
            }

    # ─── Application Timeline ────────────────────────────────────────────────

    async def get_timeline(self, job_id: str | None = None) -> list[dict]:
        """Get application timeline events (discovered → matched → applied → outcome).

        If job_id is given, returns timeline for that job only.
        Otherwise returns recent timeline across all jobs.
        """
        await self.initialize()
        async with self._session_factory() as session:
            query = select(JobRecord).order_by(JobRecord.discovered_at.desc())
            if job_id:
                query = query.where(JobRecord.id == job_id)
            else:
                query = query.limit(50)

            result = await session.execute(query)
            records = result.scalars().all()

            timeline: list[dict] = []
            for r in records:
                events = []
                if r.discovered_at:
                    events.append({"stage": "discovered", "at": r.discovered_at.isoformat()})
                if r.status in (JobStatus.MATCHED.value, JobStatus.APPLIED.value):
                    events.append({"stage": "matched", "at": r.discovered_at.isoformat(),
                                   "score": r.match_score})
                if r.applied_at:
                    events.append({"stage": "applied", "at": r.applied_at.isoformat()})
                if r.outcome:
                    events.append({"stage": r.outcome,
                                   "at": r.outcome_at.isoformat() if r.outcome_at else ""})

                timeline.append({
                    "job_id": r.id,
                    "title": r.title,
                    "company": r.company,
                    "current_status": r.status,
                    "events": events,
                })

            return timeline
