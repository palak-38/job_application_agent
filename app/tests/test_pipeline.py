from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Job, JobScore, ResumeDoc, Role
from app.services.pipeline import run_private_pipeline

FAKE_DOC = ResumeDoc(name="Palak Sood", sections=[])


def make_job(n: int) -> Job:
    return Job(
        title=f"Job {n}",
        company=f"Company {n}",
        location="Remote",
        description="Test description",
        url=f"https://example.com/job/{n}",
    )


def patch_pipeline(
    stack: ExitStack, jobs: list[Job], scores: list[tuple[Role, JobScore]]
):
    """Patch every side-effecting collaborator at the point of use and
    return the mocks that tests assert on. `scores` holds one
    (best_role, JobScore) tuple per job, in job order."""
    mocks = {
        "get_jobs": stack.enter_context(
            patch("app.services.pipeline.get_jobs", new_callable=AsyncMock,
                  return_value=jobs)
        ),
        "score_best": stack.enter_context(
            patch("app.services.pipeline.score_job_best_role",
                  new_callable=AsyncMock, side_effect=scores)
        ),
        "read_resume": stack.enter_context(
            patch("app.services.pipeline.read_resume_as_text",
                  return_value="MASTER RESUME")
        ),
        "parse_resume": stack.enter_context(
            patch("app.services.pipeline.parse_resume", return_value=FAKE_DOC)
        ),
        "tailor": stack.enter_context(
            patch("app.services.pipeline.tailor_resume",
                  new_callable=AsyncMock, return_value=(FAKE_DOC, True))
        ),
        "create_pdf": stack.enter_context(
            patch("app.services.pipeline.create_resume_pdf",
                  return_value=b"%PDF fake")
        ),
        "send_email": stack.enter_context(
            patch("app.services.pipeline.send_summary_email")
        ),
        "mark_seen": stack.enter_context(
            patch("app.services.pipeline.mark_seen")
        ),
        "record_run": stack.enter_context(
            patch("app.services.pipeline.record_run")
        ),
    }
    return mocks


@pytest.mark.asyncio
async def test_no_new_jobs_sends_no_email_and_scores_nothing():
    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs=[], scores=[])
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER)

    assert counts.jobs_scored == 0
    mocks["score_best"].assert_not_awaited()
    mocks["send_email"].assert_not_called()
    mocks["mark_seen"].assert_not_called()
    assert mocks["record_run"].call_args.kwargs["status"] == "no_new_jobs"


@pytest.mark.asyncio
async def test_gate_rewrites_only_jobs_at_or_above_threshold():
    jobs = [make_job(1), make_job(2), make_job(3)]
    scores = [
        (Role.ML_AI_ENGINEER, JobScore(score=8, reason="great fit")),
        (Role.DATA_SCIENCE, JobScore(score=4, reason="weak fit")),
        (Role.BACKEND_SWE, JobScore(score=6, reason="borderline fit")),  # == threshold
    ]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        stack.enter_context(
            patch("app.services.pipeline.settings.score_threshold", 6.0)
        )
        counts = await run_private_pipeline(role=None)

    assert counts.jobs_scored == 3
    assert counts.jobs_matched == 2
    assert counts.jobs_skipped == 1
    assert mocks["tailor"].await_count == 2
    rewritten_jobs = [c.args[1] for c in mocks["tailor"].await_args_list]
    assert [j.title for j in rewritten_jobs] == ["Job 1", "Job 3"]

    # The digest gets ALL scored jobs with their matched roles, and
    # attachments only for the matched ones.
    scored_arg, attachments_arg = mocks["send_email"].call_args.args
    assert len(scored_arg) == 3
    assert [s.matched_role for s in scored_arg] == [
        Role.ML_AI_ENGINEER, Role.DATA_SCIENCE, Role.BACKEND_SWE
    ]
    assert [s.resume_text is not None for s in scored_arg] == [True, False, True]
    assert len(attachments_arg) == 2

    # Every fetched job is marked seen, whichever side of the gate it landed on.
    mocks["mark_seen"].assert_called_once_with(jobs)
    # The run lands in history for the landing page.
    assert mocks["record_run"].call_args.kwargs["status"] == "email_sent"


@pytest.mark.asyncio
async def test_unrestricted_run_covers_all_roles_default_first():
    with ExitStack() as stack:
        mocks = patch_pipeline(
            stack, [make_job(1)],
            [(Role.ML_AI_ENGINEER, JobScore(score=2, reason="weak"))],
        )
        stack.enter_context(
            patch("app.services.pipeline.settings.default_role", Role.DATA_SCIENCE)
        )
        await run_private_pipeline(role=None)

    roles_arg = mocks["get_jobs"].call_args.kwargs["roles"]
    assert set(roles_arg) == set(Role)
    assert roles_arg[0] == Role.DATA_SCIENCE  # preference-ordered
    # Scoring considers the same preference-ordered role list.
    assert mocks["score_best"].call_args.args[1] == roles_arg


@pytest.mark.asyncio
async def test_explicit_role_restricts_fetch_and_scoring():
    with ExitStack() as stack:
        mocks = patch_pipeline(
            stack, [make_job(1)],
            [(Role.BACKEND_SWE, JobScore(score=9, reason="strong"))],
        )
        await run_private_pipeline(role=Role.BACKEND_SWE)

    assert mocks["get_jobs"].call_args.kwargs["roles"] == [Role.BACKEND_SWE]
    assert mocks["score_best"].call_args.args[1] == [Role.BACKEND_SWE]


@pytest.mark.asyncio
async def test_resume_read_once_per_matched_role():
    """Two jobs matching the same role must share one Drive read; a third
    matching a different role triggers exactly one more."""
    jobs = [make_job(1), make_job(2), make_job(3)]
    scores = [
        (Role.BACKEND_SWE, JobScore(score=8, reason="fit")),
        (Role.BACKEND_SWE, JobScore(score=7, reason="fit")),
        (Role.DATA_SCIENCE, JobScore(score=9, reason="fit")),
    ]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        counts = await run_private_pipeline(role=None)

    assert counts.jobs_matched == 3
    read_roles = [c.args[0] for c in mocks["read_resume"].call_args_list]
    assert read_roles == [Role.BACKEND_SWE, Role.DATA_SCIENCE]


@pytest.mark.asyncio
async def test_unscored_job_fails_open_without_rewrite():
    jobs = [make_job(1)]
    scores = [
        (Role.ML_AI_ENGINEER, JobScore(score=None, reason="scoring unavailable"))
    ]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        counts = await run_private_pipeline(role=None)

    assert counts.jobs_matched == 0
    assert counts.jobs_skipped == 1
    mocks["tailor"].assert_not_awaited()
    scored_arg = mocks["send_email"].call_args.args[0]
    assert scored_arg[0].score is None
    assert scored_arg[0].resume_text is None


@pytest.mark.asyncio
async def test_per_request_threshold_overrides_config_default():
    jobs = [make_job(1)]
    scores = [(Role.ML_AI_ENGINEER, JobScore(score=4, reason="weak fit"))]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        stack.enter_context(
            patch("app.services.pipeline.settings.score_threshold", 6.0)
        )
        counts = await run_private_pipeline(role=None, threshold=3.0)

    assert counts.jobs_matched == 1
    assert mocks["send_email"].call_args.kwargs["threshold"] == 3.0


@pytest.mark.asyncio
async def test_resume_not_read_when_nothing_matches():
    jobs = [make_job(1)]
    scores = [(Role.ML_AI_ENGINEER, JobScore(score=2, reason="irrelevant"))]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        counts = await run_private_pipeline(role=None)

    assert counts.jobs_matched == 0
    mocks["read_resume"].assert_not_called()
    mocks["tailor"].assert_not_awaited()
    # The digest still goes out so skipped jobs are visible.
    mocks["send_email"].assert_called_once()

