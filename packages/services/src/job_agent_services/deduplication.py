"""Semantic job deduplication — detects duplicate listings across sources.

Uses fuzzy title + company matching to identify the same job posted
on multiple boards, preventing wasted applications.

Usage:
    deduplicator = JobDeduplicator()
    unique_jobs = deduplicator.deduplicate(jobs)
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Sequence

from job_agent_contracts.models import JobListing

logger = logging.getLogger(__name__)

# Words to strip when comparing titles (noise)
_TITLE_NOISE = re.compile(
    r"\b(senior|junior|mid|lead|staff|principal|sr\.?|jr\.?|ii|iii|iv|"
    r"remote|hybrid|onsite|on-site|full-time|part-time|contract)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase, strip noise words, collapse whitespace."""
    text = _TITLE_NOISE.sub("", text.lower())
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return _WHITESPACE.sub(" ", text).strip()


def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio (0.0–1.0)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class JobDeduplicator:
    """Identifies and merges duplicate job listings from different sources.

    Two jobs are considered duplicates when:
    - Normalized company names match (>= 85% similar)
    - Normalized titles match (>= 80% similar)
    - OR same URL

    When duplicates are found, the one with more data (longer description) wins.
    """

    def __init__(
        self,
        company_threshold: float = 0.85,
        title_threshold: float = 0.80,
    ):
        self._company_threshold = company_threshold
        self._title_threshold = title_threshold

    def is_duplicate(self, job_a: JobListing, job_b: JobListing) -> bool:
        """Check if two job listings refer to the same position."""
        # Same URL is definitive
        if job_a.url and job_b.url and job_a.url == job_b.url:
            return True

        # Compare normalized company names
        company_a = _normalize(job_a.company)
        company_b = _normalize(job_b.company)
        if _similarity(company_a, company_b) < self._company_threshold:
            return False

        # Compare normalized titles
        title_a = _normalize(job_a.title)
        title_b = _normalize(job_b.title)
        return _similarity(title_a, title_b) >= self._title_threshold

    def deduplicate(self, jobs: Sequence[JobListing]) -> list[JobListing]:
        """Remove duplicate jobs, keeping the one with the richest data.

        Returns a new list with duplicates removed. O(n²) but job lists
        are typically small (<100 per search).
        """
        if not jobs:
            return []

        unique: list[JobListing] = []
        seen_urls: set[str] = set()

        for job in jobs:
            # Fast path: exact URL match
            if job.url and job.url in seen_urls:
                continue

            # Check against all unique jobs so far
            is_dup = False
            for i, existing in enumerate(unique):
                if self.is_duplicate(job, existing):
                    # Keep the one with more description content
                    if len(job.description or "") > len(existing.description or ""):
                        unique[i] = job
                        if existing.url:
                            seen_urls.discard(existing.url)
                        if job.url:
                            seen_urls.add(job.url)
                    is_dup = True
                    break

            if not is_dup:
                unique.append(job)
                if job.url:
                    seen_urls.add(job.url)

        removed = len(jobs) - len(unique)
        if removed > 0:
            logger.info("Deduplication: removed %d duplicates from %d jobs", removed, len(jobs))

        return unique
