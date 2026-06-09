import logging
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.services.pipeline import run_private_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["run"])


@router.post("/run")
async def run_pipeline():
    # if settings.app_mode != "real":
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Private pipeline is disabled in demo mode",
    #     )

    try:
        count = await run_private_pipeline()
        return {
            "status": "email_sent",
            "jobs_processed": count,
        }
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))