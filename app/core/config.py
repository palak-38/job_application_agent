# app/core/config.py
from pathlib import Path
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

from app.models.schemas import Role

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    groq_api_key: str
    adzuna_app_id: str
    adzuna_api_key: str
    google_resume_doc_id: str                    # now required
    service_account_file: str = "service_account.json"
    # Deployed hosts have no service_account.json file: paste the JSON
    # content itself into this env var instead. Takes precedence over the
    # file when set.
    google_service_account_json: str | None = None
    # Hosted dedup DB (Turso). Unset -> local sqlite file (dev/tests).
    turso_database_url: str | None = None
    turso_auth_token: str | None = None
    # When set, POST /run requires a matching X-API-Key header.
    run_token: str | None = None
    # When set, the digest goes out via the Resend HTTPS API instead of
    # Gmail SMTP (Render's free tier blocks all outbound SMTP ports).
    # Without a verified custom domain Resend only delivers to the account
    # owner's own address — which is exactly what this digest does.
    resend_api_key: str | None = None
    resend_from: str = "Job Hunter <onboarding@resend.dev>"
    sender_email: str
    gmail_app_password: str
    recipient_email: str
    default_role: Role = Role.ML_AI_ENGINEER
    score_threshold: float = 6.0        # scoring gate default; RunRequest.threshold overrides per run
    # Per-role resume Google Doc ids (D1: profile-ready). Empty = every role
    # uses google_resume_doc_id. Set as JSON, e.g.
    # ROLE_RESUME_DOC_IDS={"data_science": "<doc-id>"}
    role_resume_doc_ids: dict[Role, str] = {}
    jobs_per_run: int = 5
    sqlite_db_path: str = "seen_jobs.db"
    model_config = ConfigDict(extra="forbid", env_file=str(_ENV_FILE))


settings = Settings()