"""User profile manager - single source of truth for user data.

The resume PDF is the source of truth. Profile is:
1. Parsed from resume via LLM on first run or when file changes
2. Stored as structured JSON (data/profile.json)
3. Vectorized in ChromaDB for RAG matching
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from job_agent_contracts.interfaces import LLMProvider
from job_agent_services.stores.rag import RAGService
from job_agent_services.profile.parser import ResumeParser

logger = logging.getLogger(__name__)

RESUME_HASH_KEY = "_resume_file_hash"


class ProfileManager:
    """Manages user profile derived from resume."""

    def __init__(self, llm: LLMProvider, rag: RAGService, profile_dir: str = "data"):
        self._parser = ResumeParser(llm=llm)
        self._rag = rag
        self._profile_path = Path(profile_dir) / "profile.json"
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)

    def get_profile(self) -> dict[str, Any]:
        """Get the current user profile (from file)."""
        if self._profile_path.exists():
            return json.loads(self._profile_path.read_text(encoding="utf-8"))
        return {}

    async def ensure_profile(self, resume_path: str) -> dict[str, Any]:
        """Ensure profile is up-to-date with resume file."""
        resume_file = Path(resume_path)
        if not resume_file.exists():
            logger.warning("Resume file not found: %s", resume_path)
            return self.get_profile()

        current_hash = self._file_hash(resume_file)
        existing_profile = self.get_profile()
        stored_hash = existing_profile.get(RESUME_HASH_KEY, "")

        if current_hash == stored_hash and existing_profile:
            logger.info("Resume unchanged, using cached profile")
            return existing_profile

        logger.info("Resume changed (or first run), parsing...")
        profile = await self._parser.parse_file(str(resume_file))

        profile[RESUME_HASH_KEY] = current_hash
        profile["_last_parsed"] = datetime.now().isoformat()
        profile["_resume_path"] = str(resume_file)

        self._save_profile(profile)
        await self._vectorize_profile(profile)

        logger.info("Profile updated: %s (%d skills detected)",
                    profile.get("name", "Unknown"), len(profile.get("skills", [])))
        return profile

    async def force_refresh(self, resume_path: str) -> dict[str, Any]:
        """Force re-parse regardless of hash."""
        resume_file = Path(resume_path)
        if not resume_file.exists():
            raise FileNotFoundError(f"Resume not found: {resume_path}")

        profile = await self._parser.parse_file(str(resume_file))
        profile[RESUME_HASH_KEY] = self._file_hash(resume_file)
        profile["_last_parsed"] = datetime.now().isoformat()
        profile["_resume_path"] = str(resume_file)

        self._save_profile(profile)
        await self._vectorize_profile(profile)
        return profile

    async def _vectorize_profile(self, profile: dict[str, Any]) -> None:
        """Index profile into RAG vector store for matching."""
        profile_text = self._profile_to_text(profile)
        await self._rag.index_profile(profile_text)

        skills = profile.get("skills", [])
        if skills:
            skills_text = f"Technical and professional skills: {', '.join(skills)}"
            await self._rag.store.add(
                doc_id="user_skills",
                text=skills_text,
                metadata={"type": "profile_skills"},
            )

        for i, exp in enumerate(profile.get("experience", [])):
            exp_text = (
                f"Experience: {exp.get('title', '')} at {exp.get('company', '')}\n"
                f"Duration: {exp.get('duration', '')}\n"
                f"Highlights: {'; '.join(exp.get('highlights', []))}"
            )
            await self._rag.store.add(
                doc_id=f"user_experience_{i}",
                text=exp_text,
                metadata={"type": "profile_experience", "index": i},
            )

    def _profile_to_text(self, profile: dict[str, Any]) -> str:
        parts = [
            f"Name: {profile.get('name', '')}",
            f"Location: {profile.get('location', '')}",
            f"Years of experience: {profile.get('years_of_experience', 'N/A')}",
            f"Education: {profile.get('education', '')}",
            f"Summary: {profile.get('summary', '')}",
            f"Skills: {', '.join(profile.get('skills', []))}",
        ]
        for exp in profile.get("experience", []):
            parts.append(
                f"Worked as {exp.get('title', '')} at {exp.get('company', '')} "
                f"({exp.get('duration', '')}): {'; '.join(exp.get('highlights', []))}"
            )
        return "\n".join(parts)

    def _save_profile(self, profile: dict[str, Any]) -> None:
        self._profile_path.write_text(
            json.dumps(profile, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
