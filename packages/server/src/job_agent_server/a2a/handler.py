"""A2A (Agent-to-Agent) Protocol implementation."""

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from job_agent_contracts.models import AgentCard, TaskState

logger = logging.getLogger(__name__)


class A2AMessage(BaseModel):
    role: str
    parts: list[dict[str, Any]] = []
    timestamp: datetime = Field(default_factory=datetime.now)


class A2AArtifact(BaseModel):
    name: str
    description: str = ""
    parts: list[dict[str, Any]] = []
    mime_type: str = "application/json"


class A2ATask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    state: TaskState = TaskState.SUBMITTED
    messages: list[A2AMessage] = []
    artifacts: list[A2AArtifact] = []
    metadata: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class A2AServer:
    """A2A protocol server for agent discovery and task routing."""

    def __init__(self, agents: list[Any]):
        self._agents = {a.name: a for a in agents}
        self._tasks: dict[str, A2ATask] = {}

    def get_agent_card(self) -> dict[str, Any]:
        return {
            "name": "job-apply-agent",
            "description": "AI-powered personal job application agent",
            "version": "0.4.0",
            "url": "http://localhost:8000",
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "stateTransitionHistory": True,
            },
            "skills": [
                {"id": "search_jobs", "name": "Job Search", "description": "Search for jobs"},
                {"id": "match_profile", "name": "Profile Matching", "description": "Score job-profile fit"},
                {"id": "tailor_resume", "name": "Resume Tailoring", "description": "Generate cover letters"},
                {"id": "apply_job", "name": "Job Application", "description": "Submit applications"},
                {"id": "email_apply", "name": "Email Application", "description": "Apply via email for abroad jobs"},
            ],
            "provider": {"organization": "job-apply-agent", "url": ""},
            "authentication": {"schemes": []},
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
        }

    async def send_task(self, task_request: dict[str, Any]) -> A2ATask:
        message_data = task_request.get("message", {})
        messages = []
        if message_data:
            messages = [A2AMessage(
                role=message_data.get("role", "user"),
                parts=message_data.get("parts", []),
            )]

        task = A2ATask(
            id=task_request.get("id", str(uuid.uuid4())),
            messages=messages,
            metadata=task_request.get("metadata", {}),
        )

        self._tasks[task.id] = task
        task.state = TaskState.WORKING
        task.updated_at = datetime.now()

        try:
            result = await self._route_task(task)
            task.state = TaskState.COMPLETED
            task.artifacts.append(A2AArtifact(
                name="result",
                description="Task output",
                parts=[{"type": "text", "text": str(result)}],
            ))
        except Exception as e:
            task.state = TaskState.FAILED
            task.artifacts.append(A2AArtifact(
                name="error",
                parts=[{"type": "text", "text": str(e)}],
            ))
            logger.error("Task %s failed: %s", task.id, e)

        task.updated_at = datetime.now()
        return task

    async def get_task(self, task_id: str) -> A2ATask | None:
        return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.state in (TaskState.SUBMITTED, TaskState.WORKING):
            task.state = TaskState.CANCELED
            task.updated_at = datetime.now()
            return True
        return False

    async def _route_task(self, task: A2ATask) -> Any:
        skill_id = task.metadata.get("skill_id", "")
        agent_name = task.metadata.get("agent", "")

        if agent_name and agent_name in self._agents:
            return await self._agents[agent_name].handle_task({
                "id": task.id, "input": task.metadata.get("input", {}),
            })

        skill_to_agent = {
            "search_jobs": "job_search",
            "match_profile": "profile_matcher",
            "tailor_resume": "resume_tailor",
            "apply_job": "applicator",
        }

        target = skill_to_agent.get(skill_id)
        if target and target in self._agents:
            return await self._agents[target].handle_task({
                "id": task.id, "input": task.metadata.get("input", {}),
            })

        if "orchestrator" in self._agents:
            return await self._agents["orchestrator"].run()

        raise ValueError(f"No agent found for task: {task.id}")
