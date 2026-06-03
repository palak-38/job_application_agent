# app/core/config.py
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str | None = None
    adzuna_app_id: str
    adzuna_api_key: str
    google_resume_doc_id: str | None = None
    service_account_file: str = "service_account.json"
    sender_email: str | None = None
    gmail_app_password: str | None = None
    recipient_email: str | None = None
    job_query: str = "AI engineer"
    jobs_per_run: int = 5

    model_config = ConfigDict(extra="forbid", env_file=".env")


settings = Settings()