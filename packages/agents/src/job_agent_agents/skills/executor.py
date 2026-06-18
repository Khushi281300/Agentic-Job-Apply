"""Skill Executor - generic agentic loop for running skills.

Handles the complete lifecycle:
1. Sub-skill call (if configured)
2. Prefetch data via RAG (if configured)
3. Render prompt from template
4. Call LLM with per-skill config
5. Validate output against schema (if configured)
6. Return structured result
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from job_agent_contracts.interfaces import LLMProvider
from job_agent_contracts.skills import SkillConfig, SkillResult
from job_agent_services.stores.rag import RAGService
from job_agent_services.observability.tracing import tracer

logger = logging.getLogger(__name__)


# Output schema registry - maps schema name strings to actual Pydantic classes
_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {}


def register_output_schema(name: str, schema: type[BaseModel]) -> None:
    """Register a Pydantic model as a named output schema."""
    _SCHEMA_REGISTRY[name] = schema


def _resolve_schema(name: str) -> type[BaseModel] | None:
    """Resolve schema name to Pydantic class."""
    if not name:
        return None
    if name not in _SCHEMA_REGISTRY:
        from job_agent_contracts import models
        schema_cls = getattr(models, name, None)
        if schema_cls and isinstance(schema_cls, type) and issubclass(schema_cls, BaseModel):
            _SCHEMA_REGISTRY[name] = schema_cls
            return schema_cls
        return None
    return _SCHEMA_REGISTRY[name]


class SkillExecutor:
    """Executes skills using the configured LLM + RAG context.

    This is the generic agentic loop. All skill-specific behavior
    comes from SkillConfig — the executor itself is skill-agnostic.
    """

    def __init__(self, llm: LLMProvider, rag: RAGService | None = None):
        self.llm = llm
        self.rag = rag

    async def execute(
        self,
        config: SkillConfig,
        context: dict[str, Any],
        sub_executor: "SkillExecutor | None" = None,
    ) -> SkillResult:
        """Execute a skill with the given context."""
        start = time.time()

        async with tracer.aspan(
            f"skill.{config.name}",
            metadata={"temperature": config.llm_config.temperature},
        ) as span:
            try:
                # Step 1: Sub-skill call (if configured)
                if config.sub_skill and sub_executor:
                    sub_result = await self._run_sub_skill(config, context, sub_executor)
                    if sub_result:
                        context[config.sub_skill.output_key] = sub_result

                # Step 2: Prefetch RAG context (if configured)
                if config.prefetch and config.prefetch.rag_query_template and self.rag:
                    rag_context = await self._prefetch_rag(config, context)
                    context["rag_context"] = rag_context

                # Step 3: Render prompt from template
                from job_agent_agents.prompts import render
                prompt = render(config.user_prompt_template, **context)

                # Step 4: Call LLM with skill-specific config
                schema = _resolve_schema(config.output_schema)
                skill_model = config.llm_config.model

                if schema:
                    output = await self.llm.generate_validated(
                        prompt, schema=schema, system=config.system_prompt,
                        retries=2, task=skill_model,
                    )
                    raw_output = ""
                else:
                    output = await self.llm.generate(
                        prompt, system=config.system_prompt,
                        temperature=config.llm_config.temperature, task=skill_model,
                    )
                    raw_output = output if isinstance(output, str) else ""

                duration = (time.time() - start) * 1000
                span.outputs = {"success": True, "duration_ms": duration}

                return SkillResult(
                    skill_name=config.name, success=True,
                    output=output, raw_output=raw_output, duration_ms=duration,
                )

            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error("Skill '%s' failed: %s", config.name, e)
                span.outputs = {"success": False, "error": str(e)}

                return SkillResult(
                    skill_name=config.name, success=False,
                    error=str(e), duration_ms=duration,
                )

    async def _run_sub_skill(
        self, parent_config: SkillConfig, context: dict[str, Any],
        sub_executor: "SkillExecutor",
    ) -> Any:
        """Execute a sub-skill and return its output."""
        from job_agent_agents.skills.registry import skill_registry

        sub_config = skill_registry.resolve(parent_config.sub_skill.skill_name)
        if not sub_config:
            logger.warning("Sub-skill not found: %s", parent_config.sub_skill.skill_name)
            return None

        sub_context = {}
        for parent_key, sub_key in parent_config.sub_skill.input_mapping.items():
            if parent_key in context:
                sub_context[sub_key] = context[parent_key]

        result = await sub_executor.execute(sub_config, sub_context)
        return result.output if result.success else None

    async def _prefetch_rag(self, config: SkillConfig, context: dict[str, Any]) -> str:
        """Prefetch relevant context from RAG before LLM call."""
        try:
            query_template = config.prefetch.rag_query_template
            for key, value in context.items():
                if isinstance(value, str):
                    query_template = query_template.replace(f"{{{{{key}}}}}", value)

            results = await self.rag.store.query(query_template, top_k=3)
            if results:
                return "\n---\n".join(r.get("content", r.get("text", "")) for r in results)
        except Exception as e:
            logger.debug("RAG prefetch failed (non-fatal): %s", e)
        return ""
