"""Tailor the structured resume to a job with SURGICAL edits.

The model never regenerates the resume — wholesale rewriting flattens the
candidate's own writing into LLM-average prose (real user feedback). It
receives the ResumeDoc as indexed JSON and returns a small, validated edit
set (a job-specific summary + a handful of bullet rewrites). Anything it
can't justify editing stays exactly as the candidate wrote it.
"""

import copy
import json
import logging
import re

from pydantic import ValidationError

from app.core.config import settings
from app.integrations.groq_client import chat_completion
from app.models.schemas import Job, ResumeDoc, ResumeEdits, ResumeEntry, ResumeSection

logger = logging.getLogger(__name__)

_SUMMARY_TITLES = ("SUMMARY", "PROFILE", "OBJECTIVE", "ABOUT")

SYSTEM_PROMPT = """You are a senior resume editor. You make SURGICAL, \
minimal edits to tailor a resume to one job posting. You never rewrite the \
whole resume.

Rules you must follow without exception:
- NEVER invent facts, metrics, tools, companies, dates, or skills that are \
not in the original resume.
- The candidate is a fresher (0-1 years, one internship): never inflate \
seniority or claim years of experience.
- Edit a bullet ONLY when the job description gives a genuine reason \
(shared technology, matching responsibility). Rephrase to surface that \
overlap using the job's terminology — keep the candidate's voice, length, \
and level of detail. At most 6 bullet edits.
- Write one 2-3 line summary tailored to this job, using only facts from \
the resume.
- No buzzword filler: never use phrases like "results-driven", \
"passionate", "dynamic", "leverage synergies".

Respond with ONLY a JSON object, no markdown fences, in this exact shape:
{"summary": "<tailored summary or null>",
 "bullet_edits": [{"section": <int>, "entry": <int>, "bullet": <int>, \
"new_text": "<rewritten bullet>"}]}

Indices refer to the resume JSON you are given (0-based)."""

USER_TEMPLATE = """JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{description}

RESUME (indexed JSON):
{resume_json}"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_edits(raw: str) -> ResumeEdits | None:
    try:
        return ResumeEdits.model_validate(json.loads(_FENCE_RE.sub("", raw).strip()))
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(f"Unparseable tailoring output: {e}")
        return None


def apply_edits(doc: ResumeDoc, edits: ResumeEdits) -> ResumeDoc:
    """Apply validated edits to a copy of the doc. Out-of-range indices are
    logged and skipped — a bad edit must never corrupt the resume."""
    result = copy.deepcopy(doc)

    for edit in edits.bullet_edits:
        try:
            result.sections[edit.section].entries[edit.entry].bullets[
                edit.bullet
            ] = edit.new_text
        except IndexError:
            logger.warning(
                f"Skipped out-of-range bullet edit: section={edit.section} "
                f"entry={edit.entry} bullet={edit.bullet}"
            )

    if edits.summary:
        summary_entry = ResumeEntry(heading=edits.summary)
        for section in result.sections:
            if section.title.upper().startswith(_SUMMARY_TITLES):
                section.entries = [summary_entry]
                break
        else:
            result.sections.insert(
                0, ResumeSection(title="SUMMARY", entries=[summary_entry])
            )

    return result


async def _call_tailoring_model(resume: ResumeDoc, job: Job) -> str:
    user_message = USER_TEMPLATE.format(
        title=job.title,
        company=job.company,
        description=job.description[:3000],
        resume_json=resume.model_dump_json(),
    )
    response = await chat_completion(
        model=settings.groq_tailoring_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return response.choices[0].message.content.strip()


async def tailor_resume(resume: ResumeDoc, job: Job) -> tuple[ResumeDoc, bool]:
    """Return (tailored_doc, tailored_ok). Retries once on unparseable
    output, then fails open: the ORIGINAL resume is returned untouched —
    a matched job always ships with a resume, tailored or not."""
    for attempt in (1, 2):
        raw = await _call_tailoring_model(resume, job)
        edits = _parse_edits(raw)
        if edits is not None:
            logger.info(
                f"Tailored resume for {job.company} — {job.title}: "
                f"{len(edits.bullet_edits)} bullet edit(s), "
                f"summary={'yes' if edits.summary else 'no'}"
            )
            return apply_edits(resume, edits), True
        logger.warning(
            f"Tailoring attempt {attempt} unparseable for "
            f"{job.company} — {job.title}"
        )

    logger.warning(
        f"Tailoring unavailable for {job.company} — {job.title}; "
        "attaching original resume"
    )
    return resume, False
