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
# instructions (scale, output format) live once; only the rubric varies per
# role. Do not add per-role prompt templates.
ROLE_RUBRICS: dict[Role, str] = {
    Role.ML_AI_ENGINEER: (
        "Strong match: building/integrating LLM or GenAI applications, "
        "Python, model-API integration (OpenAI/Anthropic/open-weights), "
        "prompt engineering, RAG, vector databases, or light MLOps "
        "(serving/monitoring models). Moderate: general ML engineering with "
        "Python. Weak: pure research roles requiring a PhD, heavy "
        "distributed-training infrastructure, or non-Python stacks."
    ),
    Role.DATA_SCIENCE: (
        "Strong match: data analysis and statistical modeling with "
        "Python/SQL, building predictive models, experimentation/AB testing, "
        "and communicating insights to stakeholders. Moderate: analytics "
        "engineering or BI-heavy roles with Python. Weak: pure data-entry, "
        "roles demanding deep domain credentials (e.g. quant finance PhD), "
        "or dashboard-only tooling with no modeling."
    ),
    Role.BACKEND_SWE: (
        "Strong match: designing and building APIs/services in Python "
        "(FastAPI/Django/Flask), relational databases, testing, and "
        "deployment/CI. Moderate: full-stack roles that are backend-leaning, "
        "or backend in an adjacent language with Python welcome. Weak: "
        "frontend-heavy, mobile, or roles centered on a stack with no "
        "Python overlap."
    ),
}

SYSTEM_PROMPT = """You are a strict job-relevance screener. Given a job \
posting and a rubric for a target role, score how worthwhile the posting is \
to pursue for that role.

Scale: 0 = completely irrelevant, 5 = borderline, 10 = ideal match.

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
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
        max_tokens=60,
    )
    return response.choices[0].message.content.strip()


async def score_job(job: Job, role: Role) -> JobScore:
    """Score one job against the role's rubric. Retries once on unparseable
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
