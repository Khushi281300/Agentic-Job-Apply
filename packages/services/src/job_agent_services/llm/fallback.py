"""Multi-model LLM provider — supports fallback across multiple backends.

Wraps multiple LLMProvider instances and falls back to the next one
if the primary is unavailable (circuit breaker open, timeout, etc.).

Usage:
    primary = OllamaProvider(...)
    fallback = OpenAIProvider(...)  # or any LLMProvider
    llm = FallbackLLMProvider([primary, fallback])
"""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.errors import LLMUnavailableError

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class FallbackLLMProvider(LLMProvider):
    """Tries providers in order until one succeeds.

    If all providers fail, raises the last exception encountered.
    """

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("At least one LLM provider required")
        self._providers = providers

    async def generate(self, prompt: str, system: str = "", temperature: float = 0.7,
                       model: str = "", task: str = "") -> str:
        return await self._try_providers("generate", prompt=prompt, system=system,
                                         temperature=temperature, model=model, task=task)

    async def generate_json(self, prompt: str, system: str = "") -> dict[str, Any]:
        return await self._try_providers("generate_json", prompt=prompt, system=system)

    async def generate_validated(self, prompt: str, schema: type[T], system: str = "",
                                 retries: int = 2, model: str = "", task: str = "") -> T:
        return await self._try_providers("generate_validated", prompt=prompt, schema=schema,
                                         system=system, retries=retries, model=model, task=task)

    async def chat(self, messages: list[dict[str, str]]) -> str:
        return await self._try_providers("chat", messages=messages)

    async def embed(self, text: str) -> list[float]:
        return await self._try_providers("embed", text=text)

    async def is_available(self) -> bool:
        """True if any provider is available."""
        for provider in self._providers:
            try:
                if await provider.is_available():
                    return True
            except Exception:
                continue
        return False

    async def _try_providers(self, method: str, **kwargs: Any) -> Any:
        """Try each provider in order until one succeeds."""
        last_error: Exception | None = None

        for i, provider in enumerate(self._providers):
            try:
                fn = getattr(provider, method)
                result = await fn(**kwargs)
                if i > 0:
                    logger.info("LLM fallback: used provider #%d for %s", i + 1, method)
                return result
            except (LLMUnavailableError, Exception) as e:
                last_error = e
                provider_name = getattr(provider, "model", type(provider).__name__)
                logger.warning(
                    "LLM provider %s failed for %s: %s. Trying next...",
                    provider_name, method, e,
                )
                continue

        raise LLMUnavailableError(
            f"All {len(self._providers)} LLM providers failed. Last error: {last_error}"
        )
