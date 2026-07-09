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


class ResumeEntry(BaseModel):
    """One unit inside a section: a role/project with bullets, or a bare
    text line (summary paragraphs, skill lists) when bullets/dates are
    absent."""
    heading: str | None = None
    dates: str | None = None
    bullets: list[str] = []


class ResumeSection(BaseModel):
    title: str
    entries: list[ResumeEntry] = []


class ResumeDoc(BaseModel):
    """The resume as structured data. The LLM edits fields of this model
    (never freeform text), and the PDF renderer lays it out from here —
    so tailoring can't destroy the document's structure."""
    name: str
    contact: str | None = None
    sections: list[ResumeSection] = []


class BulletEdit(BaseModel):
    section: int
    entry: int
    bullet: int
    new_text: str


class ResumeEdits(BaseModel):
    """The complete set of changes the tailoring model may request."""
    summary: str | None = None
    bullet_edits: list[BulletEdit] = []


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
