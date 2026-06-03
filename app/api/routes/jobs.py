import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import Job
from app.services.job_scraper import get_jobs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[Job])
async def fetch_jobs():
    try:
        jobs = await get_jobs()
        return jobs
    except Exception as e:
        logger.error(f"Job fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch jobs")