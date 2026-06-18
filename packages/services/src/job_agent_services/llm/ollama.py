"""Ollama LLM provider - implements the LLMProvider interface.

Supports: text generation, JSON output, validated JSON, chat, and embeddings.
All calls are automatically traced via LangSmith when enabled.
"""

import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.errors import LLMUnavailableError
from job_agent_services.resilience import CircuitBreaker
from job_agent_services.observability.tracing import tracer

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class OllamaProvider(LLMProvider):
    """Local Ollama LLM - all AI stays on your machine.

    Supports per-call model override via `model` parameter:
        await llm.generate(prompt, model="deepseek-coder-v2")

    Configure task-specific models in .env:
        OLLAMA_MODEL=llama3.1          # default
        OLLAMA_MODEL_MATCH=mistral     # for job matching
        OLLAMA_MODEL_TAILOR=llama3.1   # for creative writing
        OLLAMA_MODEL_FORM=deepseek-coder-v2  # for form mapping
    """

    def __init__(self, base_url: str, model: str, embed_model: str = "nomic-embed-text",
                 timeout: int = 120, temperature: float = 0.7,
                 model_overrides: dict[str, str] | None = None,
                 cache_size: int = 128):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._embed_model = embed_model
        self._model_overrides = model_overrides or {}
        self._client: httpx.AsyncClient | None = None
        self._circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._cache_size = cache_size

    def resolve_model(self, model: str = "", task: str = "") -> str:
        """Resolve which model to use for a given call.

        Priority: explicit model param > task override > default model.
        """
        if model:
            return model
        if task and task in self._model_overrides:
            return self._model_overrides[task]
        return self.model

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def _cache_key(self, prompt: str, model: str, fmt: str = "") -> str:
        """Generate a cache key from prompt + model + format."""
        raw = f"{model}:{fmt}:{prompt}"
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def _cache_get(self, key: str) -> Any | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, value: Any) -> None:
        self._cache[key] = value
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def generate(self, prompt: str, system: str = "", temperature: float = 0.7,
                       model: str = "", task: str = "") -> str:
        """Generate text completion (traced, circuit-breaker protected)."""
        if self._circuit.is_open:
            raise LLMUnavailableError("ollama")

        resolved_model = self.resolve_model(model, task)

        async with tracer.aspan("llm.generate", metadata={"model": resolved_model},
                                inputs={"prompt_len": len(prompt), "system": system[:100]}) as span:
            payload: dict[str, Any] = {
                "model": resolved_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            }
            if system:
                payload["system"] = system

            try:
                client = await self._get_client()
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                result = response.json()["response"]
                self._circuit.record_success()
                span.outputs = {"response_len": len(result)}
                return result
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                self._circuit.record_failure()
                raise

    async def generate_json(self, prompt: str, system: str = "",
                            model: str = "", task: str = "") -> dict[str, Any]:
        """Generate structured JSON output (traced, cached, circuit-breaker protected)."""
        if self._circuit.is_open:
            raise LLMUnavailableError("ollama")

        resolved_model = self.resolve_model(model, task)

        # Check cache for identical prompts
        ckey = self._cache_key(prompt, resolved_model, "json")
        cached = self._cache_get(ckey)
        if cached is not None:
            return cached

        async with tracer.aspan("llm.generate_json", metadata={"model": resolved_model},
                                inputs={"prompt_len": len(prompt)}) as span:
            json_system = (system + "\n" if system else "") + (
                "You MUST respond with valid JSON only. No markdown, no explanations."
            )
            payload: dict[str, Any] = {
                "model": resolved_model,
                "prompt": prompt,
                "system": json_system,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3},
            }

            try:
                client = await self._get_client()
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                text = response.json()["response"].strip()
                self._circuit.record_success()
                result = self._parse_json(text)
                self._cache_put(ckey, result)
                span.outputs = {"keys": list(result.keys()) if result else []}
                return result
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as e:
                self._circuit.record_failure()
                raise

    async def generate_validated(self, prompt: str, schema: type[T], system: str = "",
                                 retries: int = 2, model: str = "", task: str = "") -> T:
        """Generate JSON and validate against a Pydantic schema.

        If the LLM output doesn't conform, retries with error feedback.
        """
        resolved_model = self.resolve_model(model, task)
        async with tracer.aspan("llm.generate_validated",
                                metadata={"model": resolved_model, "schema": schema.__name__},
                                inputs={"prompt_len": len(prompt), "retries": retries}) as span:
            last_error = ""
            for attempt in range(retries + 1):
                actual_prompt = prompt
                if last_error and attempt > 0:
                    actual_prompt += (
                        f"\n\nYour previous response had a validation error: {last_error}\n"
                        f"Please fix and respond with valid JSON matching this schema: "
                        f"{schema.model_json_schema()}"
                    )

                raw = await self.generate_json(actual_prompt, system=system,
                                               model=model, task=task)
                if not raw:
                    last_error = "Empty JSON response"
                    continue

                try:
                    validated = schema.model_validate(raw)
                    span.outputs = {"attempt": attempt + 1, "success": True}
                    return validated
                except ValidationError as e:
                    last_error = str(e)
                    logger.warning(
                        "LLM output validation failed (attempt %d/%d): %s",
                        attempt + 1, retries + 1, last_error[:200],
                    )

            span.outputs = {"success": False, "error": last_error[:200]}
            raise ValueError(
                f"LLM failed to produce valid {schema.__name__} after {retries + 1} attempts: {last_error}"
            )

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Multi-turn conversation (traced)."""
        async with tracer.aspan("llm.chat", metadata={"model": self.model},
                                inputs={"message_count": len(messages)}) as span:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": self.temperature},
            }

            client = await self._get_client()
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            result = response.json()["message"]["content"]
            span.outputs = {"response_len": len(result)}
            return result

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector using Ollama's embedding endpoint."""
        payload = {"model": self._embed_model, "prompt": text}
        client = await self._get_client()
        response = await client.post("/api/embeddings", json=payload)
        response.raise_for_status()
        return response.json()["embedding"]

    async def is_available(self) -> bool:
        """Check Ollama status and model availability."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code != 200:
                return False
            models = response.json().get("models", [])
            return any(m["name"].startswith(self.model) for m in models)
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List all models available in the Ollama instance."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
        except (httpx.ConnectError, httpx.TimeoutException):
            return []

    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from the Ollama registry."""
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/pull", json={"name": model_name, "stream": False},
                timeout=600.0,
            )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def ensure_models(self) -> dict[str, bool]:
        """Check all configured models are available."""
        available = await self.list_models()
        available_names = {m["name"].split(":")[0] for m in available}

        all_models = {self.model, self._embed_model}
        all_models.update(v for v in self._model_overrides.values() if v)

        return {m: any(m in name or name.startswith(m) for name in available_names)
                for m in all_models}

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Robustly parse JSON from LLM output."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            logger.error("JSON parse failed: %s", text[:200])
            return {}
