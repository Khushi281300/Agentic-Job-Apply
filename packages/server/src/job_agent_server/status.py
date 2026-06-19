"""Pipeline status tracker - records state, raw I/O, and errors.

Keeps a bounded in-memory log of pipeline activity for the status API.
Optionally persists logs to the database for historical viewing.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PipelinePhase(str, Enum):
    IDLE = "idle"
    SEARCHING = "searching"
    MATCHING = "matching"
    TAILORING = "tailoring"
    APPLYING = "applying"
    EMAILING = "emailing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IORecord:
    """Single input/output record."""
    timestamp: str
    node: str
    direction: str  # "input" | "output" | "error"
    data: Any
    duration_ms: float = 0


@dataclass
class PipelineStatus:
    """Current pipeline state."""
    phase: PipelinePhase = PipelinePhase.IDLE
    started_at: str | None = None
    last_activity: str | None = None
    current_job: dict | None = None
    stats: dict = field(default_factory=lambda: {
        "searched": 0,
        "matched": 0,
        "applied": 0,
        "emailed": 0,
        "failed": 0,
        "errors": 0,
    })

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "started_at": self.started_at,
            "last_activity": self.last_activity,
            "current_job": self.current_job,
            "stats": self.stats,
        }


class StatusTracker:
    """In-memory status tracker with bounded history and optional DB persistence.

    Usage:
        tracker = StatusTracker()
        tracker.set_phase(PipelinePhase.SEARCHING)
        tracker.record_input("search", {"titles": ["Python Dev"]})
        tracker.record_output("search", {"jobs_found": 5})
        tracker.record_error("match", "LLM timeout")
    """

    def __init__(self, max_records: int = 200):
        self._status = PipelineStatus()
        self._io_log: deque[IORecord] = deque(maxlen=max_records)
        self._errors: deque[IORecord] = deque(maxlen=50)
        self._start_times: dict[str, float] = {}
        self._db = None  # Optional Database instance for persistence
        self._run_id: str | None = None

    @property
    def status(self) -> PipelineStatus:
        return self._status

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def set_db(self, db) -> None:
        """Attach a Database instance for log persistence."""
        self._db = db

    def start_run(self) -> str:
        """Start a new pipeline run — generates a unique run_id and resets state."""
        self._run_id = uuid.uuid4().hex[:12]
        self.reset()
        return self._run_id

    def _persist_log(self, timestamp: str, node: str, direction: str,
                     data: Any, duration_ms: float = 0) -> None:
        """Fire-and-forget log persistence to DB."""
        if not self._db or not self._run_id:
            return
        message = _format_log_message(node, direction, data)
        data_str = json.dumps(data, default=str) if not isinstance(data, str) else data
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._db.save_pipeline_log(
                run_id=self._run_id,
                timestamp=timestamp,
                node=node,
                direction=direction,
                message=message,
                data=data_str,
                duration_ms=duration_ms,
            ))
        except RuntimeError:
            pass  # No event loop — skip persistence

    def set_phase(self, phase: PipelinePhase, job: dict | None = None) -> None:
        now = datetime.now().isoformat()
        self._status.phase = phase
        self._status.last_activity = now
        if job:
            self._status.current_job = job
        if phase == PipelinePhase.IDLE:
            self._status.current_job = None
        if self._status.started_at is None and phase != PipelinePhase.IDLE:
            self._status.started_at = now

    def record_input(self, node: str, data: Any) -> None:
        self._start_times[node] = time.time()
        now = datetime.now().isoformat()
        safe = _safe_serialize(data)
        self._io_log.append(IORecord(
            timestamp=now,
            node=node,
            direction="input",
            data=safe,
        ))
        self._status.last_activity = now
        self._persist_log(now, node, "input", safe)

        # Auto-advance phase based on which node starts
        _phase_map = {
            "search": PipelinePhase.SEARCHING,
            "fetch_details": PipelinePhase.SEARCHING,
            "match": PipelinePhase.MATCHING,
            "tailor": PipelinePhase.TAILORING,
            "apply": PipelinePhase.APPLYING,
            "email": PipelinePhase.EMAILING,
        }
        if node in _phase_map:
            self._status.phase = _phase_map[node]
            if self._status.started_at is None:
                self._status.started_at = self._status.last_activity

    def record_output(self, node: str, data: Any) -> None:
        duration = 0.0
        if node in self._start_times:
            duration = (time.time() - self._start_times.pop(node)) * 1000

        now = datetime.now().isoformat()
        safe_data = _safe_serialize(data)
        self._io_log.append(IORecord(
            timestamp=now,
            node=node,
            direction="output",
            data=safe_data,
            duration_ms=round(duration, 1),
        ))
        self._status.last_activity = now
        self._persist_log(now, node, "output", safe_data, round(duration, 1))

        # Auto-update stats from node output summaries
        if isinstance(safe_data, dict):
            if node == "search":
                count = safe_data.get("job_count", 0)
                if count:
                    self._status.stats["searched"] = count
            elif node == "match":
                matched = safe_data.get("matched", 0)
                if matched:
                    self._status.stats["matched"] = matched
            elif node == "apply":
                applied = safe_data.get("applied", 0)
                if applied:
                    self._status.stats["applied"] = applied

    def record_error(self, node: str, error: str | Exception) -> None:
        now = datetime.now().isoformat()
        error_str = str(error)
        record = IORecord(
            timestamp=now,
            node=node,
            direction="error",
            data=error_str,
        )
        self._io_log.append(record)
        self._errors.append(record)
        self._status.stats["errors"] += 1
        self._status.last_activity = now
        self._persist_log(now, node, "error", error_str)

    def inc_stat(self, key: str, amount: int = 1) -> None:
        if key in self._status.stats:
            self._status.stats[key] += amount

    def reset(self) -> None:
        self._status = PipelineStatus()
        self._start_times.clear()

    def get_full_status(self) -> dict:
        """Return full status payload for the API."""
        return {
            "run_id": self._run_id,
            "pipeline": self._status.to_dict(),
            "recent_io": [
                {
                    "timestamp": r.timestamp,
                    "node": r.node,
                    "direction": r.direction,
                    "data": r.data,
                    "duration_ms": r.duration_ms,
                }
                for r in list(self._io_log)[-50:]  # Last 50 records
            ],
            "errors": [
                {
                    "timestamp": r.timestamp,
                    "node": r.node,
                    "data": r.data,
                }
                for r in list(self._errors)
            ],
        }


def _format_log_message(node: str, direction: str, data: Any) -> str:
    """Generate a human-readable log message from node I/O."""
    if direction == "error":
        return f"{node.title()} failed — {data}" if isinstance(data, str) else f"{node.title()} error"

    messages = {
        ("pipeline", "input"): lambda d: f"Pipeline started — searching for {', '.join(d.get('titles', []))} in {', '.join(d.get('locations', []))}" if isinstance(d, dict) else "Pipeline started",
        ("search", "input"): "Searching for jobs across configured sources…",
        ("search", "output"): lambda d: f"Search complete — found {d.get('job_count', 0)} jobs" if isinstance(d, dict) else "Search complete",
        ("fetch_details", "input"): "Fetching full job descriptions…",
        ("fetch_details", "output"): "Job details enriched",
        ("match", "input"): "Matching jobs against profile & resume…",
        ("match", "output"): lambda d: f"Matching complete — {d.get('matched', 0)} passed threshold" if isinstance(d, dict) else "Matching complete",
        ("tailor", "input"): "Tailoring resumes for matched positions…",
        ("tailor", "output"): "Tailoring done — custom resumes generated",
        ("human_review", "input"): "Waiting for review",
        ("human_review", "output"): "Review completed",
        ("apply", "input"): "Submitting applications…",
        ("apply", "output"): lambda d: f"Applications submitted — {d.get('applied', 0)} sent" if isinstance(d, dict) else "Applications submitted",
        ("email", "input"): "Sending application emails…",
        ("email", "output"): "Emails sent",
    }
    key = (node, direction)
    msg = messages.get(key)
    if msg is None:
        return f"{node.title()} — {direction}"
    if callable(msg):
        return msg(data)
    return msg


def _safe_serialize(data: Any, max_len: int = 2000) -> Any:
    """Safely serialize data for status log, truncating large values."""
    if data is None:
        return None
    if isinstance(data, (str, int, float, bool)):
        if isinstance(data, str) and len(data) > max_len:
            return data[:max_len] + "...(truncated)"
        return data
    if isinstance(data, dict):
        return {k: _safe_serialize(v, max_len=500) for k, v in list(data.items())[:20]}
    if isinstance(data, (list, tuple)):
        items = [_safe_serialize(v, max_len=200) for v in data[:10]]
        if len(data) > 10:
            items.append(f"...({len(data)} total)")
        return items
    # Pydantic models
    if hasattr(data, "model_dump"):
        return _safe_serialize(data.model_dump(), max_len)
    return str(data)[:max_len]


# Singleton tracker
tracker = StatusTracker()
