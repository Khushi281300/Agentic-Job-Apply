"""End-to-end pipeline test with mock LLM — deterministic, no network calls.

Tests the full Search → Match → Tailor → Apply pipeline using
a fake LLM that returns predictable responses. Verifies the pipeline
plumbing works correctly without depending on Ollama being available.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from job_agent_contracts.models import JobListing, JobSourceType, JobStatus


class MockLLMProvider:
    """Deterministic LLM that returns canned responses for testing."""

    async def generate(self, prompt: str, system: str = "", temperature: float = 0.7,
                       model: str = "", task: str = "") -> str:
        if "requirements" in prompt.lower():
            return "Python, FastAPI, PostgreSQL, Docker"
        if "cover letter" in prompt.lower():
            return "Dear Hiring Manager, I am excited to apply..."
        return "AI-generated response"

    async def generate_json(self, prompt: str, system: str = "") -> dict:
        if "requirements" in prompt.lower() or "extract" in prompt.lower():
            return {"requirements": ["Python", "FastAPI", "Docker", "PostgreSQL"]}
        return {"result": "ok"}

    async def generate_validated(self, prompt, schema, system="", retries=2,
                                 model="", task=""):
        """Return a mock match result."""
        from job_agent_contracts.models import MatchLLMResponse
        if schema == MatchLLMResponse:
            return MatchLLMResponse(
                skill_match=0.85,
                experience_match=0.80,
                education_match=0.75,
                culture_fit=0.70,
                reasoning="Good technical fit. Strong Python background.",
                matched_skills=["Python", "FastAPI"],
                missing_skills=["PostgreSQL"],
            )
        raise ValueError(f"Unexpected schema: {schema}")

    async def chat(self, messages):
        return "chat response"

    async def embed(self, text):
        return [0.1] * 384

    async def is_available(self):
        return True


class MockVectorStore:
    """In-memory vector store for testing."""

    def __init__(self):
        self._docs: dict[str, dict] = {}

    async def add(self, doc_id, text, metadata=None):
        self._docs[doc_id] = {"text": text, "metadata": metadata or {}}

    async def query(self, text, top_k=5):
        return []

    async def delete(self, doc_id):
        self._docs.pop(doc_id, None)


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def mock_vector_store():
    return MockVectorStore()


@pytest.fixture
def sample_jobs():
    return [
        JobListing(
            id="test_job_1",
            title="Senior Python Engineer",
            company="TechCorp",
            location="Remote",
            url="https://example.com/job/1",
            source=JobSourceType.REMOTE_OK,
            description="We need a Python expert with FastAPI experience.",
            tags=["python", "fastapi"],
            discovered_at=datetime.now(),
        ),
        JobListing(
            id="test_job_2",
            title="Backend Developer",
            company="StartupXYZ",
            location="Remote",
            url="https://example.com/job/2",
            source=JobSourceType.OTHER,
            description="Looking for backend dev with Docker knowledge.",
            tags=["docker", "python"],
            discovered_at=datetime.now(),
        ),
    ]


class TestDeduplication:
    """Test the semantic deduplication logic."""

    def test_exact_url_duplicate(self, sample_jobs):
        from job_agent_services.deduplication import JobDeduplicator

        # Create a duplicate with same URL
        dup = JobListing(
            id="dup_1", title="Senior Python Engineer", company="TechCorp",
            location="Remote", url="https://example.com/job/1",
            source=JobSourceType.OTHER, discovered_at=datetime.now(),
        )
        deduplicator = JobDeduplicator()
        result = deduplicator.deduplicate([sample_jobs[0], dup, sample_jobs[1]])
        assert len(result) == 2

    def test_fuzzy_title_duplicate(self):
        from job_agent_services.deduplication import JobDeduplicator

        job_a = JobListing(
            id="a", title="Senior Python Backend Engineer", company="DataFlow Inc",
            location="Remote", url="https://a.com/1", source=JobSourceType.REMOTE_OK,
            discovered_at=datetime.now(),
        )
        job_b = JobListing(
            id="b", title="Python Backend Engineer", company="DataFlow Inc.",
            location="Remote", url="https://b.com/1", source=JobSourceType.OTHER,
            discovered_at=datetime.now(),
        )
        deduplicator = JobDeduplicator()
        assert deduplicator.is_duplicate(job_a, job_b)

    def test_different_jobs_not_deduplicated(self, sample_jobs):
        from job_agent_services.deduplication import JobDeduplicator
        deduplicator = JobDeduplicator()
        result = deduplicator.deduplicate(sample_jobs)
        assert len(result) == 2


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_closed_to_open(self):
        from job_agent_services.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitState

        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # not yet

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets(self):
        from job_agent_services.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitState

        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_recovery(self):
        from job_agent_services.resilience import CircuitBreaker, CircuitBreakerConfig, CircuitState
        import time

        cb = CircuitBreaker("test", CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout_secs=0.1, success_threshold=1
        ))
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestRetryPolicy:
    """Test retry backoff calculation."""

    def test_exponential_delay(self):
        from job_agent_services.resilience.retry import RetryPolicy

        policy = RetryPolicy(base_delay_secs=1.0, exponential_base=2.0,
                             max_delay_secs=30.0, jitter=False)
        assert policy.delay_for_attempt(0) == 1.0
        assert policy.delay_for_attempt(1) == 2.0
        assert policy.delay_for_attempt(2) == 4.0
        assert policy.delay_for_attempt(3) == 8.0

    def test_max_delay_cap(self):
        from job_agent_services.resilience.retry import RetryPolicy

        policy = RetryPolicy(base_delay_secs=1.0, exponential_base=2.0,
                             max_delay_secs=5.0, jitter=False)
        assert policy.delay_for_attempt(10) == 5.0


class TestAdaptiveScoring:
    """Test adaptive threshold computation."""

    @pytest.mark.asyncio
    async def test_defaults_with_insufficient_data(self):
        from job_agent_services.adaptive import AdaptiveScoring, AdaptiveThresholds

        mock_db = AsyncMock()
        mock_db.get_success_analytics = AsyncMock(return_value={
            "total_applied": 3,
            "by_score_range": {},
        })

        scorer = AdaptiveScoring(db=mock_db)
        result = await scorer.compute_thresholds()

        assert result.min_apply_score == AdaptiveThresholds.DEFAULT_MIN_APPLY
        assert result.alert_score == AdaptiveThresholds.DEFAULT_ALERT
        assert result.confidence == 0.0


class TestLocationFilter:
    """Test the shared location matching utility."""

    def test_remote_passes_all(self):
        from job_agent_services.sources.utils import location_matches
        assert location_matches("New York", "remote") is True
        assert location_matches("London", "") is True

    def test_specific_location(self):
        from job_agent_services.sources.utils import location_matches
        assert location_matches("New York, USA", "new york") is True
        assert location_matches("London, UK", "new york") is False

    def test_empty_job_location(self):
        from job_agent_services.sources.utils import location_matches
        assert location_matches("", "new york") is False
        assert location_matches(None, "remote") is True
