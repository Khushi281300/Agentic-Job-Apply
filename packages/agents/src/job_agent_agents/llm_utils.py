"""Safe LLM calling utilities — reusable wrappers with error handling.

Eliminates repeated try/except patterns around LLM calls in agents.
"""

import logging
from typing import Any, TypeVar

from job_agent_contracts.interfaces import LLMProvider

T = TypeVar("T")


class SafeLLMCaller:
    """Wraps an LLMProvider with standardized error handling and fallbacks.

    Usage:
        caller = SafeLLMCaller(llm, logger)
        result = await caller.validated(prompt, MySchema, system="...")
        data = await caller.json(prompt, system="...")
    """

    def __init__(self, llm: LLMProvider, log: logging.Logger) -> None:
        self._llm = llm
        self._log = log

    async def validated(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str = "",
        context_label: str = "",
    ) -> T | None:
        """Call generate_validated; return None on failure.

        Args:
            prompt: The prompt text.
            schema: Pydantic model class to validate against.
            system: System prompt.
            context_label: Label for log messages (e.g. job_id).
        """
        try:
            return await self._llm.generate_validated(prompt, schema=schema, system=system)
        except ValueError as e:
            self._log.error("LLM validation failed [%s]: %s", context_label, e)
            return None

    async def json(
        self,
        prompt: str,
        *,
        system: str = "",
        context_label: str = "",
    ) -> dict[str, Any]:
        """Call generate_json; return empty dict on failure.

        Args:
            prompt: The prompt text.
            system: System prompt.
            context_label: Label for log messages.
        """
        try:
            return await self._llm.generate_json(prompt, system=system)
        except Exception as e:
            self._log.warning("LLM JSON generation failed [%s]: %s", context_label, e)
            return {}

    async def text(
        self,
        prompt: str,
        *,
        system: str = "",
        context_label: str = "",
    ) -> str:
        """Call generate; return empty string on failure."""
        try:
            return await self._llm.generate(prompt, system=system)
        except Exception as e:
            self._log.warning("LLM generation failed [%s]: %s", context_label, e)
            return ""
