# app/models/schemas.py
from enum import Enum

from pydantic import BaseModel, HttpUrl
from datetime import datetime


class Role(str, Enum):
    """Canonical job-search roles. This single enum value is the dict key
    used for query resolution (Stage 1) and, later, resume selection and
    the scoring rubric (Stage 2)."""
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

class RewrittenResume(BaseModel):
    job: Job
    resume_text: str

class RunResponse(BaseModel):
    status: str
    jobs_processed: int


class RunRequest(BaseModel):
    role: Role | None = None       # caller-supplied; None -> falls back to settings.default_role
    location: str | None = None
    threshold: float | None = None  # reserved for Stage 2's scoring gate; unused/unwired here