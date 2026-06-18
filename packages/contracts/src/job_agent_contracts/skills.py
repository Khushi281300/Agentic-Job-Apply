"""Skill configuration schemas - declarative AI capabilities.

A Skill is a declarative unit of AI work:
  {prompt_template + tools + output_schema + llm_config}

SkillConfig defines WHAT to do.
SkillResult carries the output.
The SkillExecutor (in agents package) handles HOW.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Per-skill LLM configuration.

    Different skills need different model parameters:
    - Classification → low temperature (deterministic)
    - Cover letter → higher temperature (creative)
    - Form mapping → zero temperature (precise)
    """
    model: str = ""  # empty = use default from settings
    temperature: float = 0.3
    timeout: int = 120
    max_tokens: int = 4096


class SkillPrefetch(BaseModel):
    """Declarative pre-fetch: call a tool/RAG query before LLM runs."""
    rag_query_template: str = ""
    tool_name: str = ""


class SubSkillCall(BaseModel):
    """Invoke another skill first and inject its result into this skill's context."""
    skill_name: str
    input_mapping: dict[str, str] = {}
    output_key: str = "sub_skill_result"


class SkillConfig(BaseModel):
    """Complete definition of an AI skill.

    Skills are the unit of AI behavior. They define WHAT to do
    without encoding HOW the agentic loop works.
    """
    name: str
    description: str = ""

    # Prompts
    system_prompt: str
    user_prompt_template: str  # Jinja2 template with {{variable}} placeholders

    # Output
    output_schema: str = ""  # Pydantic model name from contracts.models (validated output)

    # LLM configuration
    llm_config: LLMConfig = Field(default_factory=LLMConfig)

    # Tool access (future: MCP tool whitelist)
    allowed_tools: list[str] = []

    # Pre-execution
    prefetch: SkillPrefetch | None = None
    sub_skill: SubSkillCall | None = None

    # Limits
    max_iterations: int = 3
    timeout: int = 120

    # Metadata
    tags: list[str] = []


# ─── Pre-defined LLM Configs ────────────────────────────────────────────────

LLM_PRECISE = LLMConfig(temperature=0.0)
LLM_ANALYTICAL = LLMConfig(temperature=0.2)
LLM_BALANCED = LLMConfig(temperature=0.4)
LLM_CREATIVE = LLMConfig(temperature=0.7)


class SkillResult(BaseModel):
    """Result from executing a skill."""
    skill_name: str
    success: bool = True
    output: Any = None
    raw_output: str = ""
    duration_ms: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = {}
