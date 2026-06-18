"""Abstract interfaces - dependency inversion for all services.

All agents and services depend on these interfaces, not concrete implementations.
This enables swapping Ollama for OpenAI, ChromaDB for Pinecone, etc.
"""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Interface for any LLM backend (Ollama, OpenAI, Anthropic, etc.)."""

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", temperature: float = 0.7) -> str:
        ...

    @abstractmethod
    async def generate_json(self, prompt: str, system: str = "") -> dict[str, Any]:
        ...

    @abstractmethod
    async def generate_validated(self, prompt: str, schema: type[T], system: str = "",
                                 retries: int = 2, model: str = "", task: str = "") -> T:
        """Generate JSON and validate against a Pydantic schema.

        Retries with error feedback if the LLM output doesn't conform.
        Returns a validated instance of `schema` or raises ValueError.
        """
        ...

    @abstractmethod
    async def chat(self, messages: list[dict[str, str]]) -> str:
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embeddings for RAG."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


class VectorStore(ABC):
    """Interface for vector storage (RAG retrieval)."""

    @abstractmethod
    async def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        ...

    @abstractmethod
    async def query(self, text: str, top_k: int = 5) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        ...


class JobSource(ABC):
    """Interface for job board scrapers - plugin system."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def search(self, title: str, location: str, **kwargs: Any) -> list[Any]:
        ...

    @abstractmethod
    async def fetch_details(self, url: str) -> str:
        ...


class AgentProtocol(ABC):
    """A2A-compatible agent interface.

    Based on Google's Agent-to-Agent protocol:
    - Each agent has a Card (capabilities description)
    - Agents communicate via Tasks with defined states
    """

    @property
    @abstractmethod
    def agent_card(self) -> dict[str, Any]:
        """Return A2A Agent Card describing capabilities."""
        ...

    @abstractmethod
    async def handle_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Process an A2A task and return result."""
        ...


class BrowserAutomation(ABC):
    """Interface for browser automation."""

    @abstractmethod
    async def navigate(self, url: str) -> None:
        ...

    @abstractmethod
    async def fill_form(self, field_mapping: dict[str, str]) -> bool:
        ...

    @abstractmethod
    async def click(self, selector: str) -> bool:
        ...

    @abstractmethod
    async def screenshot(self, path: str) -> None:
        ...

    @abstractmethod
    async def get_page_content(self) -> str:
        ...


class EmailSender(ABC):
    """Interface for sending emails (applications, notifications)."""

    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        body_html: str,
        attachments: list[tuple[str, bytes]] | None = None,
        reply_to: str = "",
    ) -> str:
        """Send an email and return the Message-ID."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
