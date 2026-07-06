from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import Job, Role
from app.services.scorer import (
    MAX_DESCRIPTION_CHARS,
    ROLE_RUBRICS,
    _parse_score_response,
    score_job,
)


def make_job(description: str = "Python developer needed") -> Job:
    return Job(
        title="ML Engineer",
        company="Acme Corp",
        location="Remote",
        description=description,
        url="https://example.com/job/1",
    )


def test_role_rubrics_covers_every_role():
    for role in Role:
        assert isinstance(ROLE_RUBRICS[role], str) and ROLE_RUBRICS[role]


def test_parse_valid_response():
    result = _parse_score_response("SCORE: 7\nREASON: Strong LLM focus.")
    assert result.score == 7
    assert result.reason == "Strong LLM focus."


def test_parse_is_case_insensitive_and_tolerates_padding():
    result = _parse_score_response("  score: 4 \n reason:  meh fit ")
    assert result.score == 4
    assert result.reason == "meh fit"


def test_parse_clamps_out_of_range_score():
    result = _parse_score_response("SCORE: 99\nREASON: overexcited model")
    assert result.score == 10


def test_parse_missing_reason_still_scores():
    result = _parse_score_response("SCORE: 5")
    assert result.score == 5
    assert result.reason == "(no reason given)"


def test_parse_malformed_returns_none():
    assert _parse_score_response("This job looks great, maybe an 8?") is None
    assert _parse_score_response("") is None


@pytest.mark.asyncio
async def test_score_job_retries_once_then_succeeds():
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        side_effect=["unparseable garbage", "SCORE: 8\nREASON: Good match."],
    ) as mock_call:
        result = await score_job(make_job(), Role.ML_AI_ENGINEER)

    assert mock_call.await_count == 2
    assert result.score == 8
    assert result.reason == "Good match."


@pytest.mark.asyncio
async def test_score_job_fails_open_after_two_unparseable_attempts():
    with patch(
        "app.services.scorer._call_scoring_model",
        new_callable=AsyncMock,
        side_effect=["garbage", "more garbage"],
    ) as mock_call:
        result = await score_job(make_job(), Role.ML_AI_ENGINEER)

    assert mock_call.await_count == 2
    assert result.score is None
    assert "unavailable" in result.reason


@pytest.mark.asyncio
async def test_score_job_truncates_description():
    long_description = "x" * (MAX_DESCRIPTION_CHARS * 2)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "SCORE: 6\nREASON: ok"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.scorer.get_groq_client", return_value=mock_client):
        result = await score_job(make_job(long_description), Role.BACKEND_SWE)

    assert result.score == 6
    user_message = mock_client.chat.completions.create.call_args.kwargs[
        "messages"
    ][1]["content"]
    assert "x" * MAX_DESCRIPTION_CHARS in user_message
    assert "x" * (MAX_DESCRIPTION_CHARS + 1) not in user_message
    # The rubric for the requested role is in the prompt.
    assert ROLE_RUBRICS[Role.BACKEND_SWE] in user_message
