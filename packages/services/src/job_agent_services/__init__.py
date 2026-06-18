"""Job Agent Services - infrastructure implementations.

Concrete implementations of contracts interfaces:
- LLM providers (Ollama, future: OpenAI, Anthropic)
- Vector stores (ChromaDB, future: Pinecone)
- Database (SQLite via SQLAlchemy)
- Browser automation (Playwright)
- Email (SMTP, future: Gmail API)
- Notifications (Telegram, Slack, Email)
- Observability (LangSmith)
"""

__version__ = "0.3.0"

from job_agent_services.registry import ServiceRegistry

__all__ = ["ServiceRegistry"]
