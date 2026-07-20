import json
import logging
import re

from app.core.config import settings
from app.integrations.groq_client import chat_completion
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

# One call scores a job against EVERY candidate role at once — cuts scoring
# tokens/calls ~3x vs a call per role, which matters against the free-tier
# per-model token budget.
SYSTEM_PROMPT = """You are a strict job-relevance screener. Given a job \
posting and a rubric for EACH target role, score how worthwhile the posting \
is to pursue for each role independently.

Scale: 0 = completely irrelevant, 5 = borderline, 10 = ideal match.

CANDIDATE EXPERIENCE LEVEL: {candidate_experience}.
Apply this as a hard check on top of every rubric: if the posting requires \
clearly more experience (3+ years, or senior/lead/staff/principal titles), \
cap that score at 3 no matter how well the stack matches, and say so in the \
reason. Fresher/entry-level/junior/graduate-friendly postings that fit a \
rubric deserve the top of their range.

Respond with ONLY a JSON object, no markdown fences, mapping each role key to \
its score and a one-sentence reason:
{{"<role_key>": {{"score": <integer 0-10>, "reason": "<one short sentence>"}}}}"""

USER_TEMPLATE = """ROLES AND RUBRICS:
{rubrics_block}

JOB POSTING:
TITLE: {title}
COMPANY: {company}
LOCATION: {location}
DESCRIPTION: {description}"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_batch_scores(
    raw: str, roles: list[Role]
) -> dict[Role, JobScore] | None:
    """Parse the model's per-role JSON into JobScores. Returns None if the
    payload isn't usable at all, so the caller can retry or fail open. A role
    missing from an otherwise-valid payload gets score=None (fail-open for
    that role only)."""
    try:
        data = json.loads(_FENCE_RE.sub("", raw).strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    result: dict[Role, JobScore] = {}
    for role in roles:
        entry = data.get(role.value)
        if isinstance(entry, dict) and "score" in entry:
            try:
                score = max(0, min(10, int(entry["score"])))
            except (TypeError, ValueError):
                score, reason = None, "unparseable score for this role"
            else:
                reason = str(entry.get("reason", "")).strip() or "(no reason given)"
            result[role] = JobScore(score=score, reason=reason)
        else:
            result[role] = JobScore(score=None, reason="no score returned for this role")

    # Every score missing → treat the whole payload as unusable (retry).
    if all(s.score is None for s in result.values()):
        return None
    return result


async def _call_scoring_model(job: Job, roles: list[Role]) -> str:
    rubrics_block = "\n".join(
        f"- {role.value}: {ROLE_RUBRICS[role]}" for role in roles
    )
    user_message = USER_TEMPLATE.format(
        rubrics_block=rubrics_block,
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description[:MAX_DESCRIPTION_CHARS],
    )
    response = await chat_completion(
        model=settings.groq_scoring_model,
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
        max_tokens=250,
    )
    return response.choices[0].message.content.strip()


async def score_job_best_role(
    job: Job, roles: list[Role]
) -> tuple[Role, JobScore]:
    """Score one job against every candidate role in a SINGLE batched call and
    return the best (role, score) pair. A job only needs to fit ONE of the
    user's role families to be worth surfacing; earlier roles in `roles` win
    ties (the list is ordered by preference). Retries once on an unusable
    payload, then fails open (score=None)."""
    scores: dict[Role, JobScore] | None = None
    for attempt in (1, 2):
        raw = await _call_scoring_model(job, roles)
        scores = _parse_batch_scores(raw, roles)
        if scores is not None:
            break
        logger.warning(
            f"Unparseable score output for {job.company} — {job.title} "
            f"(attempt {attempt}): {raw!r}"
        )

    if scores is None:
        return roles[0], JobScore(
            score=None, reason="scoring unavailable (unparseable model output)"
        )

    best_role = roles[0]
    for role in roles:
        best = -1 if scores[best_role].score is None else scores[best_role].score
        current = -1 if scores[role].score is None else scores[role].score
        if current > best:
            best_role = role

    best_score = scores[best_role]
    logger.info(
        f"Scored {job.company} — {job.title}: best={best_role.value} "
        f"score={best_score.score} reason={best_score.reason!r}"
    )
    return best_role, best_score
