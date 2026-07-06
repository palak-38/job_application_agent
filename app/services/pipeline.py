from app.core.store import mark_seen
from app.models.schemas import RewrittenResume, Role
from app.services.job_scraper import get_jobs
from app.services.resume_reader import read_resume_as_text
from app.services.rewriter import rewrite_resume_for_job
from app.services.doc_creator import create_resume_pdf
from app.services.mailer import send_summary_email


async def run_private_pipeline(role: Role, location: str | None = None) -> int:
    jobs = await get_jobs(role=role, location=location)
    resume_text = read_resume_as_text()

    results = []
    attachments = []

    for job in jobs:
        rewritten_resume = await rewrite_resume_for_job(resume_text, job)

        results.append(
            RewrittenResume(
                job=job,
                resume_text=rewritten_resume,
            )
        )
        attachments.append(create_resume_pdf(rewritten_resume, job))

    send_summary_email(results, attachments)

    # Mark seen only after a successful send so a failed run never
    # permanently skips a posting.
    mark_seen(jobs)
    return len(results)