import logging

from app.core.config import settings
from app.core.store import mark_seen
from app.models.schemas import ResumeDoc, Role, RunCounts, ScoredJob
from app.services.job_scraper import get_jobs
from app.services.resume_parser import parse_resume, resume_to_text
from app.services.resume_reader import read_resume_as_text
from app.services.rewriter import tailor_resume
from app.services.scorer import score_job_best_role
from app.services.doc_creator import create_resume_pdf
from app.services.mailer import send_summary_email

logger = logging.getLogger(__name__)


def _candidate_roles(role: Role | None) -> list[Role]:
    """An explicit role restricts the run to that role; no role means the
    job only has to fit ANY of the user's role families. The list is
    preference-ordered (default role first) for tie-breaking."""
    if role is not None:
        return [role]
    return sorted(Role, key=lambda r: r != settings.default_role)


async def run_private_pipeline(
    role: Role | None = None,
    location: str | None = None,
    threshold: float | None = None,
) -> RunCounts:
    effective_threshold = (
        threshold if threshold is not None else settings.score_threshold
    )
    roles = _candidate_roles(role)
    jobs = await get_jobs(roles=roles, location=location)
    if not jobs:
        logger.info("No new jobs to process — skipping scoring and digest email")
        return RunCounts(jobs_scored=0, jobs_matched=0, jobs_skipped=0)

    # Scoring gate (F5): every job gets scored against each candidate role's
    # rubric; the BEST score gates. Only jobs at or above the threshold
    # proceed to the expensive rewrite. Jobs whose score is unavailable
    # (None) fail open — shown in the digest, never rewritten.
    scored: list[ScoredJob] = []
    for job in jobs:
        matched_role, job_score = await score_job_best_role(job, roles)
        scored.append(
            ScoredJob(
                job=job,
                score=job_score.score,
                reason=job_score.reason,
                matched_role=matched_role,
            )
        )

    matched = [
        s for s in scored
        if s.score is not None and s.score >= effective_threshold
    ]
    logger.info(
        f"Scoring gate: {len(matched)}/{len(scored)} job(s) at or above "
        f"threshold {effective_threshold} (roles={[r.value for r in roles]})"
    )

    # The resume is only fetched when something passed the gate, and each
    # role's resume is read+parsed at most once per run. Tailoring makes
    # surgical edits to the structured doc; if it fails after retry, the
    # ORIGINAL resume ships instead (flagged in the digest) — a matched job
    # always gets an attachment.
    resume_cache: dict[Role, ResumeDoc] = {}
    attachments: list[bytes] = []
    for s in matched:
        resume_role = s.matched_role or roles[0]
        if resume_role not in resume_cache:
            resume_cache[resume_role] = parse_resume(
                read_resume_as_text(resume_role)
            )
        tailored_doc, tailored_ok = await tailor_resume(
            resume_cache[resume_role], s.job
        )
        s.resume_text = resume_to_text(tailored_doc)
        if not tailored_ok:
            s.reason += " (tailoring unavailable — original resume attached)"
        attachments.append(create_resume_pdf(tailored_doc, s.job))

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
