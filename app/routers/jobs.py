from fastapi import APIRouter, Query, HTTPException
from typing import List
from app.models.job import Job
from app.services.job_scraper import fetch_jobs

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/", response_model=List[Job])
async def get_jobs(
    query: str    = Query(...,       description="Job title or keywords"),
    location: str = Query("remote", description="City, country, or 'remote'"),
    limit: int    = Query(5, ge=1, le=20, description="Results per source"),
):
    jobs = await fetch_jobs(query, location, limit)
    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found")
    return jobs