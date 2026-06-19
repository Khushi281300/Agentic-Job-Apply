"""Pydantic data models - single source of truth for all data structures.

Used across agents, services, protocols, and storage.
All schemas are defined here; business logic MUST NOT create ad-hoc dicts.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─── Enums ───────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    DISCOVERED = "discovered"
    ANALYZING = "analyzing"
    MATCHED = "matched"
    REJECTED = "rejected"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    INTERVIEW = "interview"


class JobSourceType(str, Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    COMPANY_SITE = "company_site"
    REMOTE_OK = "remote_ok"
    OTHER = "other"


class ApplicationMethod(str, Enum):
    """How to apply for a job."""
    FORM = "form"         # Browser automation — fill web form
    EMAIL = "email"       # Direct email with resume + cover letter
    API = "api"           # ATS API submission (future)
    LINK_ONLY = "link"    # Just track the link, no auto-apply


class TaskState(str, Enum):
    """A2A Protocol task states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ─── Job Models ──────────────────────────────────────────────────────────────

class JobListing(BaseModel):
    id: str = ""
    title: str
    company: str
    location: str
    description: str = ""
    requirements: list[str] = []
    salary_range: str = ""
    salary_min: int = 0
    salary_max: int = 0
    job_type: str = "full-time"
    url: str
    source: JobSourceType = JobSourceType.OTHER
    tags: list[str] = []
    posted_date: datetime | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)
    status: JobStatus = JobStatus.DISCOVERED
    # Application method detection
    application_method: ApplicationMethod = ApplicationMethod.FORM
    contact_email: str = ""
    apply_instructions: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "JobListing":
        """Create a JobListing from a DB row / API dict."""
        status_val = d.get("status", "discovered")
        try:
            status = JobStatus(status_val)
        except ValueError:
            status = JobStatus.DISCOVERED
        return cls(
            id=d.get("id", ""),
            title=d["title"],
            company=d["company"],
            location=d.get("location", ""),
            url=d.get("url", ""),
            source=d.get("source", "other"),
            description=d.get("description", ""),
            status=status,
        )


class MatchResult(BaseModel):
    job_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    skill_match: float = Field(ge=0.0, le=1.0)
    experience_match: float = Field(ge=0.0, le=1.0)
    location_match: float = Field(ge=0.0, le=1.0)
    salary_match: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    matched_skills: list[str] = []
    missing_skills: list[str] = []


class TailoredResume(BaseModel):
    job_id: str
    summary: str
    highlighted_skills: list[str] = []
    cover_letter: str = ""
    customizations: dict[str, str] = {}


class ApplicationRecord(BaseModel):
    id: str = ""
    job: JobListing
    match_result: MatchResult
    tailored_resume: TailoredResume | None = None
    status: JobStatus = JobStatus.DISCOVERED
    applied_at: datetime | None = None
    method_used: ApplicationMethod = ApplicationMethod.FORM
    notes: str = ""
    error: str = ""


# ─── Agent Models ────────────────────────────────────────────────────────────

class AgentAction(BaseModel):
    """Audit log entry for agent actions."""
    agent_name: str
    action: str
    input_data: dict[str, Any] = {}
    output_data: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error: str = ""


class AgentCard(BaseModel):
    """A2A Protocol Agent Card - describes agent capabilities.

    See: https://google.github.io/A2A/
    """
    name: str
    description: str
    version: str = "1.0.0"
    url: str = ""
    capabilities: list[str] = []
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    skills: list[str] = []
    provider: str = "job-apply-agent"


# ─── RAG Models ──────────────────────────────────────────────────────────────

class RAGDocument(BaseModel):
    """Document stored in vector DB for retrieval."""
    doc_id: str
    content: str
    metadata: dict[str, Any] = {}
    doc_type: str = "general"  # job_description, application_history, profile, cover_letter


class RAGQueryResult(BaseModel):
    """Result from a RAG query."""
    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = {}


# ─── Config Schemas ──────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    """Structured user profile derived from resume parsing.

    This replaces all raw `user_config: dict` usage.
    """
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    title: str = ""
    summary: str = ""
    skills: list[str] = []
    experience_years: int = 0
    years_of_experience: int = 0  # alias for template compat
    education: list[str] = []
    certifications: list[str] = []
    languages: list[str] = []
    linkedin_url: str = ""
    portfolio_url: str = ""
    work_history: list[dict[str, str]] = []
    resume_path: str = ""

    def model_post_init(self, __context: Any) -> None:
        """Sync alias fields."""
        if self.years_of_experience == 0 and self.experience_years > 0:
            self.years_of_experience = self.experience_years
        elif self.experience_years == 0 and self.years_of_experience > 0:
            self.experience_years = self.years_of_experience

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """Build from raw profile dict, ignoring unknown/private keys."""
        filtered = {k: v for k, v in data.items() if not k.startswith("_")}
        return cls.model_validate(filtered)


class SearchConfig(BaseModel):
    """Job search configuration - replaces raw search_config dict."""
    titles: list[str] = ["Software Engineer"]
    locations: list[str] = ["Remote"]
    min_salary: int = 0
    remote_only: bool = False
    experience_level: str = ""


class ApplicationConfig(BaseModel):
    """Application settings - replaces raw app_config dict."""
    min_match_score: float = Field(default=0.6, ge=0.0, le=1.0)
    max_applications_per_day: int = Field(default=10, ge=1)
    auto_submit: bool = False
    headless: bool = True

    @field_validator("min_match_score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


# ─── LLM Response Schemas ────────────────────────────────────────────────────

class MatchLLMResponse(BaseModel):
    """Validated schema for LLM match scoring output."""
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    skill_match: float = Field(default=0.0, ge=0.0, le=1.0)
    experience_match: float = Field(default=0.0, ge=0.0, le=1.0)
    location_match: float = Field(default=0.0, ge=0.0, le=1.0)
    salary_match: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    matched_skills: list[str] = []
    missing_skills: list[str] = []


class FormMappingResponse(BaseModel):
    """Validated schema for LLM form field mapping output."""
    field_mappings: dict[str, str] = {}

    @field_validator("field_mappings")
    @classmethod
    def sanitize_mappings(cls, v: dict) -> dict[str, str]:
        """Only allow string key-value pairs, strip dangerous content."""
        return {
            str(k).strip(): str(val).strip()
            for k, val in v.items()
            if isinstance(k, str) and isinstance(val, str) and len(str(val)) < 5000
        }


class ApplicationMethodDetection(BaseModel):
    """LLM output: detected application method from job description."""
    method: ApplicationMethod = ApplicationMethod.FORM
    contact_email: str = ""
    instructions: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EmailComposition(BaseModel):
    """LLM output: composed application email."""
    subject: str
    body_html: str
    body_plain: str = ""


# ─── Pipeline Result Schemas ─────────────────────────────────────────────────

class PipelineResult(BaseModel):
    """Structured result from a pipeline run."""
    searched: int = 0
    matched: int = 0
    applied: int = 0
    emailed: int = 0
    failed: int = 0
    errors: list[str] = []


class JobMatchBundle(BaseModel):
    """A matched job with its match result and optional tailored content.

    Replaces ad-hoc {"job": dict, "match": dict, "tailored": dict} composites.
    """
    job: JobListing
    match: MatchResult
    tailored: TailoredResume | None = None


class ReviewItem(BaseModel):
    """Single item in human review queue."""
    title: str
    company: str
    score: float
    url: str
