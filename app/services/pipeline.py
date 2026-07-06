import logging

from app.core.config import settings
from app.core.store import mark_seen
from app.models.schemas import Role, RunCounts, ScoredJob
from app.services.job_scraper import get_jobs
from app.services.resume_reader import read_resume_as_text
from app.services.rewriter import rewrite_resume_for_job
from app.services.scorer import score_job
from app.services.doc_creator import create_resume_pdf
from app.services.mailer import send_summary_email

logger = logging.getLogger(__name__)


async def run_private_pipeline(
    role: Role,
    location: str | None = None,
    threshold: float | None = None,
) -> RunCounts:
    effective_threshold = (
        threshold if threshold is not None else settings.score_threshold
    )
    jobs = await get_jobs(role=role, location=location)
    if not jobs:
        logger.info("No new jobs to process — skipping scoring and digest email")
        return RunCounts(jobs_scored=0, jobs_matched=0, jobs_skipped=0)

    # Scoring gate (F5): every job gets a cheap score+reason call; only jobs
    # at or above the threshold proceed to the expensive rewrite. Jobs whose
    # score is unavailable (None) fail open — shown in the digest, never
    # rewritten.
    scored: list[ScoredJob] = []
    for job in jobs:
        job_score = await score_job(job, role)
        scored.append(
            ScoredJob(job=job, score=job_score.score, reason=job_score.reason)
        )

    matched = [
        s for s in scored
        if s.score is not None and s.score >= effective_threshold
    ]
    logger.info(
        f"Scoring gate: {len(matched)}/{len(scored)} job(s) at or above "
        f"threshold {effective_threshold}"
    )

    # The resume is only fetched when something passed the gate.
    if matched:
        resume_text = read_resume_as_text(role)
        for s in matched:
            s.resume_text = await rewrite_resume_for_job(resume_text, s.job)

    attachments = [create_resume_pdf(s.resume_text, s.job) for s in matched]

    send_summary_email(scored, attachments, threshold=effective_threshold)

    # Mark seen only after a successful send so a failed run never
    # permanently skips a posting. Sub-threshold and unscored jobs are
    # marked too: a posting is scored exactly once, never re-scored.
    mark_seen(jobs)
    return RunCounts(
        jobs_scored=len(scored),
        jobs_matched=len(matched),
        jobs_skipped=len(scored) - len(matched),
    )
