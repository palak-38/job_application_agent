# app/models/schemas.py
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class Role(str, Enum):
    """Canonical job-search roles. This single enum value is the dict key
    used for query resolution (Stage 1), and resume selection and the
    scoring rubric (Stage 2)."""
    ML_AI_ENGINEER = "ml_ai_engineer"   # primary — ML/AI Engineer, LLM roles
    DATA_SCIENCE = "data_science"       # secondary
    BACKEND_SWE = "backend_swe"         # tertiary


class Job(BaseModel):
    title: str
    company: str
    location: str
    description: str
    url: HttpUrl
    posted_at: datetime | None = None


class JobScore(BaseModel):
    """Result of one scoring call. score=None means the model's output was
    unparseable even after a retry — the job fails open (shown in the digest
    without a tailored resume) rather than being silently dropped."""
    score: int | None
    reason: str


class ScoredJob(BaseModel):
    """A job after the scoring gate. resume_text is set only for jobs that
    scored at or above the threshold and were rewritten. matched_role is the
    role family the job scored best against."""
    job: Job
    score: int | None
    reason: str
    matched_role: Role | None = None
    resume_text: str | None = None


class RunCounts(BaseModel):
    """Pipeline outcome: jobs_skipped counts everything not rewritten,
    including jobs whose score was unavailable (fail-open, no rewrite)."""
    jobs_scored: int
    jobs_matched: int
    jobs_skipped: int


class RunResponse(BaseModel):
    status: str
    jobs_scored: int
    jobs_matched: int
    jobs_skipped: int


class RunRequest(BaseModel):
    role: Role | None = None       # caller-supplied; None -> falls back to settings.default_role
    location: str | None = None
    threshold: float | None = Field(default=None, ge=0, le=10)  # None -> settings.score_threshold
