from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from groq import RateLimitError

from app.integrations import groq_client
from app.integrations.groq_client import chat_completion


def make_rate_limit_error(retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(
        status_code=429,
        headers=headers,
        request=httpx.Request("POST", "https://api.groq.com/v1/chat"),
    )
    return RateLimitError("rate limited", response=response, body=None)


@pytest.fixture(autouse=True)
def _instant_sleep():
    # Never actually sleep during the backoff tests.
    with patch("app.integrations.groq_client.asyncio.sleep", new_callable=AsyncMock):
        yield


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    ok = MagicMock()
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=[make_rate_limit_error(), make_rate_limit_error(), ok]
    )

    with patch.object(groq_client, "get_groq_client", return_value=fake_client):
        result = await chat_completion(model="m", messages=[])

    assert result is ok
    assert fake_client.chat.completions.create.await_count == 3


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_and_reraises():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=make_rate_limit_error()
    )

    with patch.object(groq_client, "get_groq_client", return_value=fake_client):
        with pytest.raises(RateLimitError):
            await chat_completion(model="m", messages=[])

    assert (
        fake_client.chat.completions.create.await_count
        == groq_client._MAX_ATTEMPTS
    )


@pytest.mark.asyncio
async def test_honors_retry_after_header():
    ok = MagicMock()
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=[make_rate_limit_error(retry_after="3"), ok]
    )

    with patch.object(groq_client, "get_groq_client", return_value=fake_client), patch(
        "app.integrations.groq_client.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        await chat_completion(model="m", messages=[])

    mock_sleep.assert_awaited_once_with(3.0)
