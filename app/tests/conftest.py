import os

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("ADZUNA_APP_ID", "test")
os.environ.setdefault("ADZUNA_API_KEY", "test")
os.environ.setdefault("GOOGLE_RESUME_DOC_ID", "test_doc_id")
os.environ.setdefault("SENDER_EMAIL", "test@test.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "testpassword")
os.environ.setdefault("RECIPIENT_EMAIL", "test@test.com")
os.environ.setdefault("JOBS_PER_RUN", "5")

# Hard-override (not setdefault) the settings that flip code onto live
# network paths. The developer's real .env may legitimately set these —
# e.g. RESEND_API_KEY sent test emails to api.resend.com from the suite
# before this guard existed. Real env vars outrank .env in
# pydantic-settings, and empty string is falsy where these are checked.
os.environ["RESEND_API_KEY"] = ""
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["RUN_TOKEN"] = ""
