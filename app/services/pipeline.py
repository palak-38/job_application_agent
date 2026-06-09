from app.models.schemas import RewrittenResume
from app.services.job_scraper import get_jobs
from app.services.resume_reader import read_resume_as_text
from app.services.rewriter import rewrite_resume_for_job
# from app.services.doc_creator import create_resume_doc
from app.services.mailer import send_summary_email


async def run_private_pipeline() -> int:
    jobs = await get_jobs()
    resume_text = read_resume_as_text()

    results = []

    for job in jobs:
        rewritten_resume = await rewrite_resume_for_job(resume_text, job)

        results.append(
            RewrittenResume(
                job=job,
                resume_text=rewritten_resume,
                doc_url=None,
            )
        )

    send_summary_email(results)
    return len(results)