"""Base agent class with A2A protocol support and shared infrastructure.

All agents inherit from this and get:
- LLM access (via interface, not concrete class)
- RAG context retrieval
- Event publishing
- A2A-compatible task handling
- Action audit logging
"""

import logging
from abc import abstractmethod
from typing import Any

from job_agent_contracts.events import Event, EventBus, EventType, event_bus
from job_agent_contracts.interfaces import AgentProtocol, LLMProvider
from job_agent_contracts.models import AgentAction, AgentCard, TaskState
from job_agent_services.stores.rag import RAGService


class BaseAgent(AgentProtocol):
    """Base class for all agents - implements A2A protocol."""

    def __init__(
        self,
        name: str,
        llm: LLMProvider,
        rag: RAGService | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")
        self.llm = llm
        self.rag = rag
        self.bus = bus or event_bus

        self.actions: list[AgentAction] = []

    # ─── A2A Protocol ────────────────────────────────────────────────────────

    @property
    def agent_card(self) -> dict[str, Any]:
        """A2A Agent Card - override in subclasses for specific capabilities."""
        card = AgentCard(
            name=self.name,
            description=f"Agent: {self.name}",
            capabilities=self._capabilities(),
            skills=self._skills(),
        )
        return card.model_dump()

    @abstractmethod
    def _capabilities(self) -> list[str]:
        ...

    @abstractmethod
    def _skills(self) -> list[str]:
        ...

    async def handle_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """A2A task handler - dispatches to run() with proper lifecycle."""
        task_id = task.get("id", "unknown")
        try:
            await self._emit(EventType.AGENT_STARTED, {"task_id": task_id})
            result = await self.run(**task.get("input", {}))
            await self._emit(EventType.AGENT_COMPLETED, {"task_id": task_id})
            return {"id": task_id, "state": TaskState.COMPLETED.value, "output": result}
        except Exception as e:
            await self._emit(EventType.AGENT_ERROR, {"task_id": task_id, "error": str(e)})
            return {"id": task_id, "state": TaskState.FAILED.value, "error": str(e)}

    # ─── Core Methods ────────────────────────────────────────────────────────

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's main task."""
        ...

    # ─── Shared Utilities ────────────────────────────────────────────────────

    async def _emit(self, event_type: EventType, data: dict | None = None) -> None:
        """Publish an event to the bus."""
        await self.bus.publish(Event(type=event_type, data=data or {}, source=self.name))

    async def _get_rag_context(self, query: str) -> str:
        """Retrieve RAG context if available."""
        if self.rag:
            return await self.rag.get_relevant_context(query)
        return ""

    def log_action(self, action: str, input_data: dict | None = None,
                   output_data: dict | None = None, success: bool = True,
                   error: str = "") -> None:
        """Record an action for audit trail."""
        record = AgentAction(
            agent_name=self.name,
            action=action,
            input_data=input_data or {},
            output_data=output_data or {},
            success=success,
            error=error,
        )
        self.actions.append(record)
        if success:
            self.logger.info("Action: %s completed", action)
        else:
            self.logger.error("Action: %s failed: %s", action, error)
