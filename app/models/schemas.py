# app/models/schemas.py
from pydantic import BaseModel, HttpUrl
from datetime import datetime

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
    doc_url: HttpUrl | None = None

class RunResponse(BaseModel):
    status: str
    jobs_processed: int
    results: list[RewrittenResume]