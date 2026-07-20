import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import Job, Role
from app.services.scorer import (
    MAX_DESCRIPTION_CHARS,
    ROLE_RUBRICS,
    _parse_batch_scores,
    score_job_best_role,
)


def make_job(description: str = "Python developer needed") -> Job:
    return Job(
        title="ML Engineer",
        company="Acme Corp",
        location="Remote",
        description=description,
        url="https://example.com/job/1",
    )


def batch_json(**by_role_value) -> str:
    """Build a model-style batched score payload from role_value=(score, reason)."""
    return json.dumps(
        {rv: {"score": s, "reason": r} for rv, (s, r) in by_role_value.items()}
    )


def test_role_rubrics_covers_every_role():
    for role in Role:
        assert isinstance(ROLE_RUBRICS[role], str) and ROLE_RUBRICS[role]


def test_parse_batch_valid():
    raw = batch_json(
        ml_ai_engineer=(2, "not ML"),
        data_science=(5, "some data"),
        backend_swe=(8, "strong backend"),
    )
    result = _parse_batch_scores(raw, list(Role))
    assert result[Role.BACKEND_SWE].score == 8
    assert result[Role.BACKEND_SWE].reason == "strong backend"
    assert result[Role.ML_AI_ENGINEER].score == 2


def test_parse_batch_strips_fences_and_clamps():
    raw = "```json\n" + batch_json(backend_swe=(99, "overexcited")) + "\n```"
    result = _parse_batch_scores(raw, [Role.BACKEND_SWE])
    assert result[Role.BACKEND_SWE].score == 10  # clamped


def test_parse_batch_missing_role_fails_open_for_that_role_only():
    raw = batch_json(ml_ai_engineer=(7, "good"))  # other two absent
    result = _parse_batch_scores(raw, list(Role))
    assert result[Role.ML_AI_ENGINEER].score == 7
    assert result[Role.DATA_SCIENCE].score is None
    assert result[Role.BACKEND_SWE].score is None


def test_parse_batch_all_missing_returns_none():
    # Valid JSON but none of the requested roles present -> unusable, retry.
    assert _parse_batch_scores('{"unrelated": {"score": 5}}', list(Role)) is None


def test_parse_batch_malformed_returns_none():
    assert _parse_batch_scores("not json at all", list(Role)) is None
    assert _parse_batch_scores("", list(Role)) is None
    assert _parse_batch_scores("[1, 2, 3]", list(Role)) is None  # not a dict


@pytest.mark.asyncio
async def test_score_retries_once_then_succeeds():
    good = batch_json(ml_ai_engineer=(8, "Good match."))
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        side_effect=["unparseable garbage", good],
    ) as mock_call:
        role, score = await score_job_best_role(make_job(), [Role.ML_AI_ENGINEER])

    assert mock_call.await_count == 2
    assert score.score == 8
    assert score.reason == "Good match."


@pytest.mark.asyncio
async def test_score_fails_open_after_two_unparseable_attempts():
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        side_effect=["garbage", "more garbage"],
    ) as mock_call:
        role, score = await score_job_best_role(make_job(), list(Role))

    assert mock_call.await_count == 2
    assert score.score is None
    assert "unavailable" in score.reason
    assert role == list(Role)[0]  # falls back to preferred role


@pytest.mark.asyncio
async def test_best_role_picks_highest_score_from_one_call():
    raw = batch_json(
        ml_ai_engineer=(2, "not ML"),
        data_science=(5, "some data work"),
        backend_swe=(8, "strong backend fit"),
    )
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        return_value=raw,
    ) as mock_call:
        role, score = await score_job_best_role(make_job(), list(Role))

    mock_call.assert_awaited_once()  # ONE call scores all three roles
    assert role == Role.BACKEND_SWE
    assert score.score == 8


@pytest.mark.asyncio
async def test_best_role_tie_goes_to_earlier_preference():
    raw = batch_json(data_science=(7, "equal"), backend_swe=(7, "equal"))
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        return_value=raw,
    ):
        role, _ = await score_job_best_role(
            make_job(), [Role.DATA_SCIENCE, Role.BACKEND_SWE]
        )

    assert role == Role.DATA_SCIENCE


@pytest.mark.asyncio
async def test_scoring_call_uses_scoring_model_and_truncates_and_includes_invariants():
    long_description = "x" * (MAX_DESCRIPTION_CHARS * 2)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = batch_json(backend_swe=(6, "ok"))

    with patch(
        "app.services.scorer.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_chat:
        role, score = await score_job_best_role(
            make_job(long_description), [Role.BACKEND_SWE]
        )

    assert score.score == 6
    kwargs = mock_chat.call_args.kwargs
    from app.core.config import settings
    assert kwargs["model"] == settings.groq_scoring_model
    user_message = kwargs["messages"][1]["content"]
    assert "x" * MAX_DESCRIPTION_CHARS in user_message
    assert "x" * (MAX_DESCRIPTION_CHARS + 1) not in user_message
    assert ROLE_RUBRICS[Role.BACKEND_SWE] in user_message
    # The candidate's experience level is a scoring invariant (fresher check).
    assert "fresher" in kwargs["messages"][0]["content"]
