"""Custom exception hierarchy for the job-apply-agent system.

All packages raise these typed exceptions instead of generic ValueError/RuntimeError.
This enables precise error handling and recovery strategies.
"""


class JobAgentError(Exception):
    """Base exception for all job-agent errors."""

    def __init__(self, message: str = "", recoverable: bool = False):
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)


class LLMError(JobAgentError):
    """LLM provider errors (timeout, invalid response, rate limit)."""
    pass


class LLMUnavailableError(LLMError):
    """LLM provider is not reachable (circuit breaker open)."""

    def __init__(self, provider: str = "unknown"):
        super().__init__(f"LLM provider '{provider}' is unavailable", recoverable=True)


class LLMValidationError(LLMError):
    """LLM output did not conform to expected schema."""

    def __init__(self, schema_name: str = "", raw_output: str = ""):
        self.schema_name = schema_name
        self.raw_output = raw_output[:500]
        super().__init__(f"LLM output failed validation for schema '{schema_name}'", recoverable=True)


class StorageError(JobAgentError):
    """Database or vector store errors."""
    pass


class BrowserError(JobAgentError):
    """Browser automation errors (navigation, form fill, timeout)."""
    pass


class EmailError(JobAgentError):
    """Email sending errors (SMTP, auth, rate limit)."""
    pass


class ConfigError(JobAgentError):
    """Configuration errors (missing env vars, invalid values)."""
    pass


class SkillError(JobAgentError):
    """Skill execution errors."""

    def __init__(self, skill_name: str = "", message: str = ""):
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' failed: {message}")


class ValidationError(JobAgentError):
    """Pre-execution validation failure."""

    def __init__(self, message: str = "", field: str = ""):
        self.field = field
        super().__init__(message, recoverable=True)
