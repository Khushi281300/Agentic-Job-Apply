"""Pipeline status tracker - records state, raw I/O, and errors.

Keeps a bounded in-memory log of pipeline activity for the status API.
"""

from __future__ import annotations

import time
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
    """In-memory status tracker with bounded history.

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

    @property
    def status(self) -> PipelineStatus:
        return self._status

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
        self._io_log.append(IORecord(
            timestamp=datetime.now().isoformat(),
            node=node,
            direction="input",
            data=_safe_serialize(data),
        ))
        self._status.last_activity = datetime.now().isoformat()

    def record_output(self, node: str, data: Any) -> None:
        duration = 0.0
        if node in self._start_times:
            duration = (time.time() - self._start_times.pop(node)) * 1000
        self._io_log.append(IORecord(
            timestamp=datetime.now().isoformat(),
            node=node,
            direction="output",
            data=_safe_serialize(data),
            duration_ms=round(duration, 1),
        ))
        self._status.last_activity = datetime.now().isoformat()

    def record_error(self, node: str, error: str | Exception) -> None:
        record = IORecord(
            timestamp=datetime.now().isoformat(),
            node=node,
            direction="error",
            data=str(error),
        )
        self._io_log.append(record)
        self._errors.append(record)
        self._status.stats["errors"] += 1
        self._status.last_activity = datetime.now().isoformat()

    def inc_stat(self, key: str, amount: int = 1) -> None:
        if key in self._status.stats:
            self._status.stats[key] += amount

    def reset(self) -> None:
        self._status = PipelineStatus()
        self._start_times.clear()

    def get_full_status(self) -> dict:
        """Return full status payload for the API."""
        return {
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
