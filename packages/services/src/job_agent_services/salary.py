"""Salary insights — aggregates compensation data from scraped jobs.

Computes market salary ranges for the user's target roles based on
actual data collected from job listings.

Usage:
    insights = SalaryInsights(db=db)
    report = await insights.get_market_ranges()
"""

import logging
import re
from collections import defaultdict
from typing import Any

from job_agent_services.stores.sqlite import Database

logger = logging.getLogger(__name__)

# Common salary extraction patterns
_SALARY_PATTERNS = [
    re.compile(r"\$\s*([\d,]+)\s*[-–—to]+\s*\$?\s*([\d,]+)", re.IGNORECASE),
    re.compile(r"([\d,]+)\s*[-–—to]+\s*([\d,]+)\s*(?:k|K)", re.IGNORECASE),
    re.compile(r"\$\s*([\d,]+)\s*(?:k|K)", re.IGNORECASE),
]


def _parse_salary_value(text: str) -> int:
    """Parse a salary string into an integer."""
    cleaned = text.replace(",", "").replace("$", "").strip()
    try:
        value = int(cleaned)
        # If value looks like it's in thousands (< 1000), multiply
        if value < 1000:
            value *= 1000
        return value
    except ValueError:
        return 0


class SalaryInsights:
    """Aggregates salary data from job listings to show market ranges."""

    def __init__(self, db: Database):
        self._db = db

    async def get_market_ranges(self) -> dict[str, Any]:
        """Compute salary statistics from collected job data.

        Returns ranges grouped by role category.
        """
        all_jobs = await self._db.get_all_jobs_detailed()

        salaries_by_role: dict[str, list[tuple[int, int]]] = defaultdict(list)
        total_with_salary = 0

        for job in all_jobs:
            salary_range = self._extract_salary(job)
            if salary_range:
                role_key = self._categorize_role(job.get("title", ""))
                salaries_by_role[role_key].append(salary_range)
                total_with_salary += 1

        # Compute statistics per role
        ranges: dict[str, dict] = {}
        for role, salary_list in salaries_by_role.items():
            mins = [s[0] for s in salary_list]
            maxes = [s[1] for s in salary_list]

            ranges[role] = {
                "count": len(salary_list),
                "min": min(mins),
                "max": max(maxes),
                "median_low": sorted(mins)[len(mins) // 2] if mins else 0,
                "median_high": sorted(maxes)[len(maxes) // 2] if maxes else 0,
                "avg_low": sum(mins) // len(mins) if mins else 0,
                "avg_high": sum(maxes) // len(maxes) if maxes else 0,
            }

        return {
            "total_jobs_analyzed": len(all_jobs),
            "jobs_with_salary": total_with_salary,
            "coverage_pct": round(total_with_salary / max(len(all_jobs), 1) * 100, 1),
            "ranges_by_role": ranges,
        }

    def _extract_salary(self, job: dict) -> tuple[int, int] | None:
        """Extract salary range from job data.

        Checks explicit salary fields first, then parses from description.
        """
        import json

        # Check raw_data for explicit salary fields
        raw = job.get("raw_data", "{}")
        try:
            raw_data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            raw_data = {}

        salary_min = raw_data.get("salary_min", 0)
        salary_max = raw_data.get("salary_max", 0)

        if salary_min and salary_max:
            return (int(salary_min), int(salary_max))

        # Parse from description text
        description = job.get("description", "") or ""
        for pattern in _SALARY_PATTERNS:
            match = pattern.search(description[:2000])
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    low = _parse_salary_value(groups[0])
                    high = _parse_salary_value(groups[1])
                    if low and high and low < high:
                        return (low, high)
                elif len(groups) == 1:
                    value = _parse_salary_value(groups[0])
                    if value:
                        return (int(value * 0.9), int(value * 1.1))

        return None

    def _categorize_role(self, title: str) -> str:
        """Categorize a job title into a broad role bucket."""
        title_lower = title.lower()

        categories = {
            "Backend Engineer": ["backend", "server", "api", "python developer"],
            "Frontend Engineer": ["frontend", "front-end", "react", "vue", "angular"],
            "Full Stack Engineer": ["full stack", "fullstack", "full-stack"],
            "DevOps/SRE": ["devops", "sre", "infrastructure", "platform"],
            "Data Engineer": ["data engineer", "etl", "pipeline", "data platform"],
            "ML/AI Engineer": ["machine learning", "ml engineer", "ai engineer", "nlp"],
            "Engineering Manager": ["engineering manager", "tech lead", "team lead"],
            "Software Engineer": ["software engineer", "software developer", "sde"],
        }

        for category, keywords in categories.items():
            if any(kw in title_lower for kw in keywords):
                return category

        return "Software Engineer"  # Default bucket
