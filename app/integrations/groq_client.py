import asyncio
import logging

from groq import AsyncGroq, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncGroq | None = None

# Free tier is 8k tokens/min PER model; a burst can exceed it for longer than
# the SDK's default 2 retries cover. Back off explicitly. Sleeps are capped so
# the whole chain stays well under Render's ~100s request budget.
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = [2, 4, 8]


def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
        logger.info("Groq client initialised")
    return _client


def _retry_after(error: RateLimitError, fallback: float) -> float:
    """Honor the Retry-After header Groq returns on a 429 when present."""
    try:
        value = error.response.headers.get("retry-after")
        if value is not None:
            return min(float(value), 10.0)
    except Exception:
        pass
    return fallback


async def chat_completion(**kwargs):
    """Single choke point for every Groq call: retries on 429 with backoff.
    On the final attempt the error propagates so the caller's own fail-open
    logic (unparseable/None) still runs."""
    client = get_groq_client()
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            if attempt == _MAX_ATTEMPTS - 1:
                logger.error(f"Rate limit persisted after {_MAX_ATTEMPTS} attempts")
                raise
            wait = _retry_after(e, _BACKOFF_SECONDS[attempt])
            logger.warning(
                f"Rate limited (attempt {attempt + 1}/{_MAX_ATTEMPTS}); "
                f"retrying in {wait}s"
            )
            await asyncio.sleep(wait)
