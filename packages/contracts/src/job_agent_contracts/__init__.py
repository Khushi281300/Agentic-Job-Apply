"""Job Agent Contracts - shared interfaces, models, and events.

This package defines the API boundary that all other packages depend on.
It contains ONLY abstract interfaces and data models — no implementations.
"""

__version__ = "0.3.0"

from job_agent_contracts.interfaces import (
    AgentProtocol,
    BrowserAutomation,
    JobSource,
    LLMProvider,
    VectorStore,
)
from job_agent_contracts.models import (
    ApplicationMethod,
    ApplicationRecord,
    JobListing,
    JobStatus,
    MatchResult,
    TailoredResume,
    UserProfile,
)
from job_agent_contracts.events import EventBus, EventType

__all__ = [
    "AgentProtocol",
    "ApplicationMethod",
    "ApplicationRecord",
    "BrowserAutomation",
    "EventBus",
    "EventType",
    "JobListing",
    "JobSource",
    "JobStatus",
    "LLMProvider",
    "MatchResult",
    "TailoredResume",
    "UserProfile",
    "VectorStore",
]
