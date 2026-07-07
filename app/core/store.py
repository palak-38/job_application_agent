"""Persistent, cross-run deduplication.

A job is identified by its URL. `filter_unseen` drops jobs recorded in a prior
run; `mark_seen` records them. Jobs are marked seen only after they have been
successfully delivered (see pipeline), so a failed run never permanently skips a
posting, and a second run the same day processes zero already-seen jobs.

Two backends behind one connection function, same SQL for both (Turso speaks
the SQLite dialect):
- local (default): stdlib sqlite3 file — zero setup for dev and tests.
- production: Turso hosted libSQL, used when TURSO_DATABASE_URL is set —
  free-tier hosts have ephemeral filesystems, so a local DB file would be
  wiped on every restart and the daily digest would re-send the same jobs.
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

_backend_logged = False


def _log_backend_once(backend: str) -> None:
    global _backend_logged
    if not _backend_logged:
        logger.info(f"Dedup store backend: {backend}")
        _backend_logged = True


@contextmanager
def _connect(db_path: str | None = None):
    # An explicit db_path (tests) always means local sqlite.
    if db_path is None and settings.turso_database_url:
        import libsql  # lazy: only production needs the dependency

        _log_backend_once("turso")
        conn = libsql.connect(
            settings.turso_database_url,
            auth_token=settings.turso_auth_token or "",
        )
    else:
        _log_backend_once("sqlite (local file)")
        conn = sqlite3.connect(db_path or settings.sqlite_db_path)

    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def filter_unseen(jobs: list[Job], db_path: str | None = None) -> list[Job]:
    """Return only jobs whose URL was not recorded in a prior run."""
    if not jobs:
        return []

    urls = [str(job.url) for job in jobs]
    placeholders = ",".join("?" * len(urls))
    # One query for all URLs: with a hosted backend every statement is a
    # network round-trip, so per-job SELECTs would be N+1 over the wire.
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT url FROM seen_jobs WHERE url IN ({placeholders})", urls
        ).fetchall()

    seen = {row[0] for row in rows}
    unseen = [job for job in jobs if str(job.url) not in seen]
    if seen:
        logger.info(f"Dedup: skipped {len(seen)} already-seen job(s)")
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
