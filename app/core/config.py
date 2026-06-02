# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    adzuna_app_id: str
    adzuna_api_key: str
    google_resume_doc_id: str
    service_account_file: str = "service_account.json"
    sender_email: str
    gmail_app_password: str
    recipient_email: str
    job_query: str = "software engineer"
    jobs_per_run: int = 5

    class Config:
        env_file = ".env"

settings = Settings()