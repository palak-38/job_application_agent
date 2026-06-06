import logging
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
        logger.info("Groq client initialised")
    return _client