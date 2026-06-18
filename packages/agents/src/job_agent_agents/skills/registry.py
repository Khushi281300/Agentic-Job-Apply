"""Skill Registry - resolves skill names to configs."""

from __future__ import annotations

import logging
from typing import Any

from job_agent_contracts.skills import SkillConfig
from job_agent_agents.skills.definitions import (
    SKILL_CLASSIFY_JOB,
    SKILL_COVER_LETTER,
    SKILL_DETECT_APPLICATION_METHOD,
    SKILL_COMPOSE_APPLICATION_EMAIL,
    SKILL_FORM_MAPPING,
    SKILL_MATCH_JOB,
    SKILL_PLAN_APPLICATION,
    SKILL_TAILOR_SUMMARY,
)

logger = logging.getLogger(__name__)


# Task key → skill name mapping
TASK_TO_SKILL: dict[str, str] = {
    "MATCH": "match_job",
    "CLASSIFY": "classify_job",
    "TAILOR_SUMMARY": "tailor_summary",
    "COVER_LETTER": "cover_letter",
    "FORM_MAPPING": "form_mapping",
    "PLAN": "plan_application",
    "DETECT_METHOD": "detect_application_method",
    "COMPOSE_EMAIL": "compose_application_email",
}


class SkillRegistry:
    """Central registry for all available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillConfig] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in skill definitions."""
        for skill in [
            SKILL_MATCH_JOB,
            SKILL_FORM_MAPPING,
            SKILL_TAILOR_SUMMARY,
            SKILL_COVER_LETTER,
            SKILL_CLASSIFY_JOB,
            SKILL_PLAN_APPLICATION,
            SKILL_DETECT_APPLICATION_METHOD,
            SKILL_COMPOSE_APPLICATION_EMAIL,
        ]:
            self.register(skill)

    def register(self, config: SkillConfig) -> None:
        """Register a skill config."""
        if config.name in self._skills:
            logger.debug("Overwriting skill: %s", config.name)
        self._skills[config.name] = config

    def resolve(self, name_or_task: str) -> SkillConfig | None:
        """Resolve a skill by name or task key."""
        if name_or_task in self._skills:
            return self._skills[name_or_task]

        skill_name = TASK_TO_SKILL.get(name_or_task.upper())
        if skill_name and skill_name in self._skills:
            return self._skills[skill_name]

        logger.warning("Skill not found: %s", name_or_task)
        return None

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def get_all(self) -> dict[str, SkillConfig]:
        return dict(self._skills)


# Module-level singleton
skill_registry = SkillRegistry()
