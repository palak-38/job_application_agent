# tests/conftest.py
import os
os.environ.setdefault("ADZUNA_APP_ID", "test")
os.environ.setdefault("ADZUNA_API_KEY", "test")
os.environ.setdefault("JOB_QUERY", "software engineer")
os.environ.setdefault("JOBS_PER_RUN", "5")