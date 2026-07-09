import logging

from app.core.config import settings
from app.integrations.groq_client import get_groq_client
from app.models.schemas import Job

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior resume writer. Your only job is to rewrite \
the candidate's resume to match the job description provided.

Rules you must follow without exception:
- NEVER invent facts, metrics, companies, dates, or skills not in the original resume.
- Match keywords and terminology from the job description exactly.
- Every bullet point must start with an action verb.
- Preserve all real experience, education, and skills from the original.
- Return ONLY the rewritten resume text. No preamble, no commentary, \
no explanations, no markdown fences.

Output format (the text is rendered to PDF, so follow it exactly):
- First line: the candidate's full name, alone.
- Second line: contact details on one line, if present in the original.
- Section headers in ALL CAPS on their own line (e.g. SUMMARY, EXPERIENCE, \
SKILLS, EDUCATION, PROJECTS), with one blank line before each.
- Bullet points start with "- ".
- Plain text only: no markdown symbols (#, *, _), no tables, no columns."""


async def rewrite_resume_for_job(resume_text: str, job: Job) -> str:
    client = get_groq_client()

    user_message = (
        f"JOB TITLE: {job.title}\n"
        f"COMPANY: {job.company}\n"
        f"JOB DESCRIPTION:\n{job.description}\n\n"
        f"MY CURRENT RESUME:\n{resume_text}"
    )

    response = await client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    result = response.choices[0].message.content.strip()
    logger.info(f"Resume rewritten for {job.company} — {job.title} ({len(result)} chars)")
    return result