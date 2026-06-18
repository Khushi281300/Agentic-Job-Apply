"""Configuration management using pydantic-settings.

.env holds system/infrastructure config.
User profile data lives in data/profile.json (auto-generated from resume).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLLAMA_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    embed_model: str = "nomic-embed-text"
    temperature: float = 0.7
    timeout: int = 120

    # Per-task model overrides
    model_match: str = ""
    model_tailor: str = ""
    model_form: str = ""
    model_classify: str = ""
    model_chat: str = ""

    def get_model_for_task(self, task: str) -> str:
        task_map = {
            "match": self.model_match,
            "tailor": self.model_tailor,
            "form": self.model_form,
            "classify": self.model_classify,
            "chat": self.model_chat,
        }
        return task_map.get(task, "") or self.model


class JobSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOB_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    titles: list[str] = ["Software Engineer"]
    locations: list[str] = ["Remote"]
    min_salary: int = 0
    experience_level: str = "mid"
    job_types: list[str] = ["full-time"]
    excluded_companies: list[str] = []
    keywords: list[str] = []


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    auto_submit: bool = False
    max_applications_per_day: int = 10
    search_interval_minutes: int = 60
    min_match_score: float = 0.6
    headless: bool = True


class EmailApplicationSettings(BaseSettings):
    """Settings for sending job applications via email."""
    model_config = SettingsConfigDict(env_prefix="EMAIL_APP_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    display_name: str = ""
    signature_html: str = ""
    max_per_hour: int = 10
    use_tls: bool = True


class LangSmithSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LANGSMITH_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enabled: bool = False
    api_key: str = ""
    project: str = "job-apply-agent"
    tracing_v2: bool = True


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOTIFY_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enabled: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    slack_webhook_url: str = ""
    email_smtp_host: str = ""
    email_from: str = ""
    email_to: str = ""
    email_password: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Infrastructure
    ollama: OllamaSettings = OllamaSettings()
    search: JobSearchSettings = JobSearchSettings()
    application: ApplicationSettings = ApplicationSettings()
    email_app: EmailApplicationSettings = EmailApplicationSettings()
    langsmith: LangSmithSettings = LangSmithSettings()
    notifications: NotificationSettings = NotificationSettings()

    # Paths
    resume_path: str = "data/resume.pdf"
    db_path: str = "data/applications.db"
    vectordb_path: str = "data/vectordb"

    # System
    log_level: str = "INFO"
    server_port: int = 8000
    notifications_enabled: bool = False


def load_settings() -> Settings:
    """Load settings from environment / .env file."""
    return Settings()
