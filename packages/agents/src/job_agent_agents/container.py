"""Dependency injection container - wires all components together.

Creates service instances and injects them into agents.
This is the ONLY place that knows about concrete implementations.
"""

import os

from job_agent_agents.config import Settings, load_settings
from job_agent_contracts.models import ApplicationConfig, SearchConfig, UserProfile
from job_agent_services.llm.ollama import OllamaProvider
from job_agent_services.stores.sqlite import Database
from job_agent_services.stores.chroma import ChromaRAGStore
from job_agent_services.stores.rag import RAGService
from job_agent_services.observability.tracing import tracer
from job_agent_services.email.sender import SMTPEmailSender
from job_agent_services.email.applicant import EmailApplicantService
from job_agent_services.http.client import http_client
from job_agent_services.notifications.service import NotificationService
from job_agent_services.sources.remoteok import RemoteOKSource
from job_agent_services.sources.remotive import RemotiveSource
from job_agent_services.sources.remoterocketship import RemoteRocketshipSource
from job_agent_services.sources.loader import load_sources_from_yaml, get_rate_limits_from_yaml
from job_agent_services.sources.rate_limiter import source_rate_limiter


class Container:
    """DI container that builds the full application graph."""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Initialize tracing
        tracer.configure(
            api_key=settings.langsmith.api_key,
            project=settings.langsmith.project,
            enabled=settings.langsmith.enabled,
        )

        # Core services
        self.llm = OllamaProvider(
            base_url=settings.ollama.base_url,
            model=settings.ollama.model,
            embed_model=settings.ollama.embed_model,
            timeout=settings.ollama.timeout,
            temperature=settings.ollama.temperature,
            model_overrides={
                "match": settings.ollama.model_match,
                "tailor": settings.ollama.model_tailor,
                "form": settings.ollama.model_form,
                "classify": settings.ollama.model_classify,
                "chat": settings.ollama.model_chat,
            },
        )
        self.db = Database(db_path=settings.db_path)
        self.vector_store = ChromaRAGStore(persist_dir=settings.vectordb_path)
        self.rag = RAGService(llm=self.llm, store=self.vector_store)

        # Email application service (for abroad jobs)
        self.email_applicant: EmailApplicantService | None = None
        if settings.email_app.smtp_host:
            sender = SMTPEmailSender(
                smtp_host=settings.email_app.smtp_host,
                smtp_port=settings.email_app.smtp_port,
                username=settings.email_app.username,
                password=settings.email_app.password,
                from_email=settings.email_app.from_email,
                display_name=settings.email_app.display_name,
                use_tls=settings.email_app.use_tls,
            )
            self.email_applicant = EmailApplicantService(
                sender=sender,
                max_per_hour=settings.email_app.max_per_hour,
                signature_html=settings.email_app.signature_html,
            )

        # Skill executor
        from job_agent_agents.skills.executor import SkillExecutor
        self.skill_executor = SkillExecutor(llm=self.llm, rag=self.rag)

        # Job sources: hardcoded Python sources + YAML-driven generic sources
        self.job_sources = [RemoteOKSource(), RemotiveSource(), RemoteRocketshipSource()]
        yaml_sources = load_sources_from_yaml()
        self.job_sources.extend(yaml_sources)

        # Register YAML rate limits into the global rate limiter
        yaml_limits = get_rate_limits_from_yaml()
        for src_name, limit in yaml_limits.items():
            source_rate_limiter._limits[src_name] = limit

        # Notification service (for high-match alerts, errors)
        self.notifier = NotificationService(
            telegram_token=getattr(settings, 'telegram_token', '') or os.environ.get('TELEGRAM_TOKEN', ''),
            telegram_chat_id=getattr(settings, 'telegram_chat_id', '') or os.environ.get('TELEGRAM_CHAT_ID', ''),
            slack_webhook_url=getattr(settings, 'slack_webhook', '') or os.environ.get('SLACK_WEBHOOK_URL', ''),
        )

        # Config → domain models
        self._search_config = SearchConfig(
            titles=settings.search.titles,
            locations=settings.search.locations,
            min_salary=settings.search.min_salary,
        )
        self._app_config = ApplicationConfig(
            min_match_score=settings.application.min_match_score,
            max_applications_per_day=settings.application.max_applications_per_day,
            auto_submit=settings.application.auto_submit,
            headless=settings.application.headless,
        )

        # Orchestrator (contains all agents) - lazy loaded
        self._orchestrator = None

    @property
    def orchestrator(self):
        """Lazy-load orchestrator to avoid circular imports."""
        if self._orchestrator is None:
            from job_agent_agents.orchestrator import Orchestrator
            from job_agent_services.profile.manager import ProfileManager

            profile_manager = ProfileManager(llm=self.llm, rag=self.rag)

            self._orchestrator = Orchestrator(
                llm=self.llm,
                db=self.db,
                rag=self.rag,
                user_profile=UserProfile.from_dict(profile_manager.get_profile()),
                search_config=self._search_config,
                app_config=self._app_config,
                job_sources=self.job_sources,
                email_applicant=self.email_applicant,
                notifier=self.notifier if self.notifier.is_configured else None,
            )
        return self._orchestrator

    async def startup(self) -> None:
        """Initialize async services."""
        await self.db.initialize()

    async def shutdown(self) -> None:
        """Cleanup resources."""
        if hasattr(self.llm, 'close'):
            await self.llm.close()
        await http_client.close()


def build_container() -> Container:
    """Build the DI container from settings."""
    settings = load_settings()
    return Container(settings)
