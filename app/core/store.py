"""Persistent, cross-run deduplication backed by SQLite (stdlib, no new dep).

A job is identified by its URL. `filter_unseen` drops jobs recorded in a prior
run; `mark_seen` records them. Jobs are marked seen only after they have been
successfully delivered (see pipeline), so a failed run never permanently skips a
posting, and a second run the same day processes zero already-seen jobs.
"""

import logging
import sqlite3
from contextlib import contextmanager

from app.core.config import settings
from app.models.schemas import Job

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    url     TEXT PRIMARY KEY,
    company TEXT,
    title   TEXT,
    seen_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


@contextmanager
def _connect(db_path: str | None = None):
    conn = sqlite3.connect(db_path or settings.sqlite_db_path)
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def filter_unseen(jobs: list[Job], db_path: str | None = None) -> list[Job]:
    """Return only jobs whose URL was not recorded in a prior run."""
    with _connect(db_path) as conn:
        unseen = [
            job
            for job in jobs
            if conn.execute(
                "SELECT 1 FROM seen_jobs WHERE url = ?", (str(job.url),)
            ).fetchone()
            is None
        ]

    skipped = len(jobs) - len(unseen)
    if skipped:
        logger.info(f"Dedup: skipped {skipped} already-seen job(s)")
    return unseen


def mark_seen(jobs: list[Job], db_path: str | None = None) -> None:
    """Record jobs so future runs never re-process them."""
    if not jobs:
        return

    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (url, company, title) VALUES (?, ?, ?)",
            [(str(job.url), job.company, job.title) for job in jobs],
        )
    logger.info(f"Dedup: recorded {len(jobs)} job(s) as seen")
