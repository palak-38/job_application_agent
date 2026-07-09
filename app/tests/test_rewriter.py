import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.services.rewriter import rewrite_resume_for_job
from app.models.schemas import Job


def make_test_job() -> Job:
    return Job(
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        description="We need a Python developer with FastAPI experience.",
        url="https://example.com/job/1",
    )


@pytest.mark.asyncio
async def test_rewriter_returns_string():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "Rewritten resume content here"

    with patch("app.services.rewriter.get_groq_client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(
            return_value=fake_response
        )
        mock_client.return_value = mock_instance

        result = await rewrite_resume_for_job("Original resume text", make_test_job())

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_rewriter_returns_stripped_content():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "  Rewritten resume  \n"

    with patch("app.services.rewriter.get_groq_client") as mock_client:
        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(
            return_value=fake_response
        )
        mock_client.return_value = mock_instance

        result = await rewrite_resume_for_job("Original resume text", make_test_job())

    assert result == "Rewritten resume"


@pytest.mark.asyncio
async def test_rewriter_passes_correct_model():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "Rewritten resume"

    with patch("app.services.rewriter.get_groq_client") as mock_client:
        mock_instance = MagicMock()
        create_mock = AsyncMock(return_value=fake_response)
        mock_instance.chat.completions.create = create_mock
        mock_client.return_value = mock_instance

        await rewrite_resume_for_job("Original resume text", make_test_job())

    call_kwargs = create_mock.call_args.kwargs
    assert call_kwargs["model"] == settings.groq_model  # configurable, not hardcoded
    assert call_kwargs["temperature"] == 0.3