from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Job, JobScore, Role
from app.services.pipeline import run_private_pipeline


def make_job(n: int) -> Job:
    return Job(
        title=f"Job {n}",
        company=f"Company {n}",
        location="Remote",
        description="Test description",
        url=f"https://example.com/job/{n}",
    )


def patch_pipeline(stack: ExitStack, jobs: list[Job], scores: list[JobScore]):
    """Patch every side-effecting collaborator at the point of use and
    return the mocks that tests assert on."""
    mocks = {
        "get_jobs": stack.enter_context(
            patch("app.services.pipeline.get_jobs", new_callable=AsyncMock,
                  return_value=jobs)
        ),
        "score_job": stack.enter_context(
            patch("app.services.pipeline.score_job", new_callable=AsyncMock,
                  side_effect=scores)
        ),
        "read_resume": stack.enter_context(
            patch("app.services.pipeline.read_resume_as_text",
                  return_value="MASTER RESUME")
        ),
        "rewrite": stack.enter_context(
            patch("app.services.pipeline.rewrite_resume_for_job",
                  new_callable=AsyncMock, return_value="tailored resume")
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
    }
    return mocks


@pytest.mark.asyncio
async def test_no_new_jobs_sends_no_email_and_scores_nothing():
    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs=[], scores=[])
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER)

    assert counts.jobs_scored == 0
    mocks["score_job"].assert_not_awaited()
    mocks["send_email"].assert_not_called()
    mocks["mark_seen"].assert_not_called()


@pytest.mark.asyncio
async def test_gate_rewrites_only_jobs_at_or_above_threshold():
    jobs = [make_job(1), make_job(2), make_job(3)]
    scores = [
        JobScore(score=8, reason="great fit"),
        JobScore(score=4, reason="weak fit"),
        JobScore(score=6, reason="borderline fit"),  # == threshold -> passes
    ]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        stack.enter_context(
            patch("app.services.pipeline.settings.score_threshold", 6.0)
        )
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER)

    assert counts.jobs_scored == 3
    assert counts.jobs_matched == 2
    assert counts.jobs_skipped == 1
    assert mocks["rewrite"].await_count == 2
    rewritten_jobs = [c.args[1] for c in mocks["rewrite"].await_args_list]
    assert [j.title for j in rewritten_jobs] == ["Job 1", "Job 3"]

    # The digest gets ALL scored jobs (skipped visibly included), with
    # attachments only for the matched ones.
    scored_arg, attachments_arg = mocks["send_email"].call_args.args
    assert len(scored_arg) == 3
    assert [s.resume_text is not None for s in scored_arg] == [True, False, True]
    assert len(attachments_arg) == 2
    assert mocks["send_email"].call_args.kwargs["threshold"] == 6.0

    # Every fetched job is marked seen, whichever side of the gate it landed on.
    mocks["mark_seen"].assert_called_once_with(jobs)


@pytest.mark.asyncio
async def test_unscored_job_fails_open_without_rewrite():
    jobs = [make_job(1)]
    scores = [JobScore(score=None, reason="scoring unavailable")]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER)

    assert counts.jobs_matched == 0
    assert counts.jobs_skipped == 1
    mocks["rewrite"].assert_not_awaited()
    scored_arg = mocks["send_email"].call_args.args[0]
    assert scored_arg[0].score is None
    assert scored_arg[0].resume_text is None


@pytest.mark.asyncio
async def test_per_request_threshold_overrides_config_default():
    jobs = [make_job(1)]
    scores = [JobScore(score=4, reason="weak fit")]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        stack.enter_context(
            patch("app.services.pipeline.settings.score_threshold", 6.0)
        )
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER, threshold=3.0)

    assert counts.jobs_matched == 1
    assert mocks["send_email"].call_args.kwargs["threshold"] == 3.0


@pytest.mark.asyncio
async def test_resume_not_read_when_nothing_matches():
    jobs = [make_job(1)]
    scores = [JobScore(score=2, reason="irrelevant")]

    with ExitStack() as stack:
        mocks = patch_pipeline(stack, jobs, scores)
        counts = await run_private_pipeline(role=Role.ML_AI_ENGINEER)

    assert counts.jobs_matched == 0
    mocks["read_resume"].assert_not_called()
    mocks["rewrite"].assert_not_awaited()
    # The digest still goes out so skipped jobs are visible.
    mocks["send_email"].assert_called_once()
