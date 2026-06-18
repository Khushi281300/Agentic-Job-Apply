"""Audit trail - append-only execution history for the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """Single audit entry - what happened at a pipeline step."""
    node_name: str
    status: str = "success"  # success | failed | skipped | retried
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0
    input_summary: dict[str, Any] = {}
    output_summary: dict[str, Any] = {}
    error: str = ""
    retry_count: int = 0
    metadata: dict[str, Any] = {}


class AuditTrail(BaseModel):
    """Complete audit trail for a pipeline run."""
    session_id: str = ""
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    history: list[AuditEntry] = []
    errors: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self.history.append(entry)
        if entry.status == "failed":
            self.errors.append(entry)
