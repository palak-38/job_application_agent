from pydantic import BaseModel
from typing import Optional

class Job(BaseModel):
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
    posted_date: Optional[str] = None