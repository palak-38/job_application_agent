import logging
from fastapi import APIRouter, Depends, Header, HTTPException
from app.core.config import settings
from app.models.schemas import RunRequest, RunResponse
from app.services.pipeline import run_private_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["run"])


async def verify_run_token(x_api_key: str | None = Header(default=None)) -> None:
    """Guard for a public deployment: /run has cost side effects (LLM calls,
    email), so when RUN_TOKEN is configured the caller must present it.
    Unset (local dev) leaves the endpoint open."""
    if settings.run_token and x_api_key != settings.run_token:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post("/run", response_model=RunResponse, dependencies=[Depends(verify_run_token)])
async def run_pipeline(request: RunRequest = RunRequest()):
    role = request.role or settings.default_role
    logger.info(f"Run requested: caller_role={request.role}, effective_role={role.value}")

    try:
        counts = await run_private_pipeline(
            role=role, location=request.location, threshold=request.threshold
        )
        status = "email_sent" if counts.jobs_scored else "no_new_jobs"
        return RunResponse(status=status, **counts.model_dump())
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))