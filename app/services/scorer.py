import asyncio
import logging
import re

from app.core.config import settings
from app.integrations.groq_client import get_groq_client
from app.models.schemas import Job, JobScore, Role

logger = logging.getLogger(__name__)

# Descriptions are truncated before scoring: the score only needs the gist,
# and this keeps the cheap gating call cheap.
MAX_DESCRIPTION_CHARS = 1500

# One prompt template + a rubric dict keyed by the Role enum — the invariant
# instructions (scale, output format, experience check) live once; only the
# rubric varies per role. Do not add per-role prompt templates.
#
# Rubrics score transferability, not exact stack match: an adjacent stack is
# a mid-range score, not a zero — the gate exists to drop irrelevant
# postings, not defensible ones.
ROLE_RUBRICS: dict[Role, str] = {
    Role.ML_AI_ENGINEER: (
        "Strong (7-10): building/integrating LLM or GenAI applications, "
        "Python, model-API integration, prompt engineering, RAG, vector "
        "databases, or light MLOps. Moderate (4-6): general ML/AI work "
        "where Python or the specific stack differs but the skills "
        "transfer (e.g. ML in another language, data-heavy backend). "
        "Weak (0-3): unrelated disciplines — pure research demanding a "
        "PhD, non-technical roles, no ML/AI content at all."
    ),
    Role.DATA_SCIENCE: (
        "Strong (7-10): data analysis and statistical modeling with "
        "Python/SQL, predictive models, experimentation/AB testing, "
        "insight communication. Moderate (4-6): analytics engineering, "
        "BI-heavy roles, or data roles on an adjacent stack where the "
        "skills transfer. Weak (0-3): pure data entry, roles demanding "
        "deep specialist credentials, no data content."
    ),
    Role.BACKEND_SWE: (
        "Strong (7-10): designing/building APIs and services in Python "
        "(FastAPI/Django/Flask), relational databases, testing, "
        "deployment/CI. Moderate (4-6): backend or full-stack work in an "
        "adjacent language (Node/Java/Go/TypeScript) where the "
        "engineering skills transfer. Weak (0-3): frontend-only, mobile, "
        "or non-engineering roles."
    ),
}

SYSTEM_PROMPT = """You are a strict job-relevance screener. Given a job \
posting and a rubric for a target role, score how worthwhile the posting is \
to pursue for that role.

Scale: 0 = completely irrelevant, 5 = borderline, 10 = ideal match.

CANDIDATE EXPERIENCE LEVEL: {candidate_experience}.
Apply this as a hard check on top of the rubric: if the posting requires \
clearly more experience (3+ years, or senior/lead/staff/principal titles), \
cap the score at 3 no matter how well the stack matches, and say so in the \
reason. Fresher/entry-level/junior/graduate-friendly postings that fit the \
rubric deserve the top of their range.

Respond with EXACTLY two lines and nothing else:
SCORE: <integer 0-10>
REASON: <one short sentence>"""

USER_TEMPLATE = """TARGET ROLE: {role}

RUBRIC FOR THIS ROLE:
{role_rubric}

JOB POSTING:
TITLE: {title}
COMPANY: {company}
LOCATION: {location}
DESCRIPTION: {description}"""

_SCORE_RE = re.compile(r"SCORE:\s*(\d{1,2})", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


def _parse_score_response(text: str) -> JobScore | None:
    """Parse the model's 'SCORE: n / REASON: ...' output. Returns None when
    no score can be extracted, so the caller can retry or fail open."""
    score_match = _SCORE_RE.search(text)
    if not score_match:
        return None

    score = max(0, min(10, int(score_match.group(1))))
    reason_match = _REASON_RE.search(text)
    reason = reason_match.group(1).strip() if reason_match else "(no reason given)"
    return JobScore(score=score, reason=reason)


async def _call_scoring_model(job: Job, role: Role) -> str:
    client = get_groq_client()
    user_message = USER_TEMPLATE.format(
        role=role.value,
        role_rubric=ROLE_RUBRICS[role],
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description[:MAX_DESCRIPTION_CHARS],
    )
    response = await client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    candidate_experience=settings.candidate_experience
                ),
            },
            {"role": "user", "content": user_message},
        ],
        temperature=0,
        max_tokens=60,
    )
    return response.choices[0].message.content.strip()


async def score_job(job: Job, role: Role) -> JobScore:
    """Score one job against one role's rubric. Retries once on unparseable
    output, then fails open (score=None) — a scoring hiccup must never kill
    the run or silently hide a posting."""
    for attempt in (1, 2):
        raw = await _call_scoring_model(job, role)
        parsed = _parse_score_response(raw)
        if parsed is not None:
            logger.info(
                f"Scored {job.company} — {job.title}: role={role.value} "
                f"score={parsed.score} reason={parsed.reason!r}"
            )
            return parsed
        logger.warning(
            f"Unparseable score output for {job.company} — {job.title} "
            f"(attempt {attempt}): {raw!r}"
        )

    return JobScore(
        score=None, reason="scoring unavailable (unparseable model output)"
    )


async def score_job_best_role(
    job: Job, roles: list[Role]
) -> tuple[Role, JobScore]:
    """Score one job against every candidate role in parallel and return the
    best (role, score) pair. A job only needs to fit ONE of the user's role
    families to be worth surfacing; earlier roles in `roles` win ties (the
    list is ordered by preference)."""
    scores = await asyncio.gather(*(score_job(job, role) for role in roles))

    best_role, best_score = roles[0], scores[0]
    for role, job_score in zip(roles[1:], scores[1:]):
        best = -1 if best_score.score is None else best_score.score
        current = -1 if job_score.score is None else job_score.score
        if current > best:
            best_role, best_score = role, job_score

    logger.info(
        f"Best role for {job.company} — {job.title}: {best_role.value} "
        f"({best_score.score})"
    )
    return best_role, best_score
