"""Tests for core models."""

import pytest
from datetime import datetime
from job_agent_contracts.models import (
    JobListing, JobStatus, JobSourceType, MatchResult,
    TailoredResume, AgentCard, TaskState, RAGDocument,
)


class TestJobListing:
    def test_create_minimal(self):
        job = JobListing(title="Engineer", company="Acme", location="Remote", url="https://example.com")
        assert job.title == "Engineer"
        assert job.status == JobStatus.DISCOVERED
        assert job.source == JobSourceType.OTHER

    def test_create_full(self):
        job = JobListing(
            id="abc123",
            title="Senior Python Dev",
            company="BigCorp",
            location="NYC",
            description="Build things",
            requirements=["Python", "AWS"],
            salary_range="$120k-$160k",
            job_type="full-time",
            url="https://bigcorp.com/jobs/1",
            source=JobSourceType.LINKEDIN,
        )
        assert job.id == "abc123"
        assert len(job.requirements) == 2
        assert job.source == JobSourceType.LINKEDIN

    def test_default_discovered_at(self):
        job = JobListing(title="Test", company="Co", location="LA", url="http://x.com")
        assert isinstance(job.discovered_at, datetime)


class TestMatchResult:
    def test_valid_scores(self):
        match = MatchResult(
            job_id="abc",
            overall_score=0.85,
            skill_match=0.9,
            experience_match=0.8,
            location_match=1.0,
            salary_match=0.7,
        )
        assert match.overall_score == 0.85

    def test_score_bounds(self):
        with pytest.raises(Exception):
            MatchResult(job_id="abc", overall_score=1.5, skill_match=0, experience_match=0, location_match=0, salary_match=0)

    def test_matched_skills(self):
        match = MatchResult(
            job_id="x",
            overall_score=0.7,
            skill_match=0.8,
            experience_match=0.6,
            location_match=1.0,
            salary_match=0.5,
            matched_skills=["Python", "Docker"],
            missing_skills=["Kubernetes"],
        )
        assert "Python" in match.matched_skills
        assert "Kubernetes" in match.missing_skills


class TestTailoredResume:
    def test_create(self):
        t = TailoredResume(job_id="abc", summary="Experienced dev", cover_letter="Dear...")
        assert t.job_id == "abc"
        assert t.highlighted_skills == []


class TestAgentCard:
    def test_create(self):
        card = AgentCard(
            name="test_agent",
            description="A test",
            capabilities=["search"],
            skills=["web_scraping"],
        )
        assert card.name == "test_agent"
        assert card.version == "1.0.0"


class TestTaskState:
    def test_states(self):
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.COMPLETED == "completed"
        assert TaskState.FAILED == "failed"
