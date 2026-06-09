# app/core/config.py
from pathlib import Path
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    groq_api_key: str
    adzuna_app_id: str
    adzuna_api_key: str
    google_resume_doc_id: str                    # now required
    service_account_file: str = "service_account.json"
    sender_email: str | None = None
    gmail_app_password: str | None = None
    recipient_email: str | None = None
    job_query: str = "software engineer"
    jobs_per_run: int = 5

    model_config = ConfigDict(extra="forbid", env_file=str(_ENV_FILE))


settings = Settings()