"""Event bus for decoupled inter-agent communication.

Agents publish events; other agents/services subscribe.
This replaces tight coupling between agents.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Job lifecycle
    JOB_DISCOVERED = "job.discovered"
    JOB_DETAILS_FETCHED = "job.details_fetched"
    JOB_MATCHED = "job.matched"
    JOB_REJECTED = "job.rejected"
    JOB_APPLYING = "job.applying"
    JOB_APPLIED = "job.applied"
    JOB_FAILED = "job.failed"
    # Email application
    JOB_EMAILED = "job.emailed"
    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    # System
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    RAG_INDEXED = "rag.indexed"
    AGENT_MESSAGE = "agent.message"
    OUTCOME_RECORDED = "outcome.recorded"


@dataclass
class Event:
    """Immutable event object passed through the bus."""
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async publish-subscribe event bus for agent coordination.

    Usage:
        bus = EventBus()
        bus.subscribe(EventType.JOB_DISCOVERED, my_handler)
        await bus.publish(Event(type=EventType.JOB_DISCOVERED, data={...}))
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._history: list[Event] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed %s to %s", handler.__name__, event_type.value)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a handler."""
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        self._history.append(event)
        handlers = self._handlers.get(event.type, [])
        logger.debug("Publishing %s to %d handlers", event.type.value, len(handlers))

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("Handler %s failed for %s: %s", handler.__name__, event.type.value, e)

    def get_history(self, event_type: EventType | None = None) -> list[Event]:
        """Get event history, optionally filtered by type."""
        if event_type:
            return [e for e in self._history if e.type == event_type]
        return self._history.copy()


# Global event bus singleton
event_bus = EventBus()
