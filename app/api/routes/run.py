import logging
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.models.schemas import RunRequest, RunResponse
from app.services.pipeline import run_private_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["run"])


@router.post("/run", response_model=RunResponse)
async def run_pipeline(request: RunRequest = RunRequest()):
    role = request.role or settings.default_role
    logger.info(f"Run requested: caller_role={request.role}, effective_role={role.value}")

    try:
        count = await run_private_pipeline(role=role, location=request.location)
        return RunResponse(status="email_sent", jobs_processed=count)
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))