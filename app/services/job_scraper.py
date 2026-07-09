import asyncio
import logging
import re
from datetime import datetime, timezone

import feedparser
import httpx

from app.core.config import settings
from app.core.store import filter_unseen
from app.models.schemas import Job, Role

logger = logging.getLogger(__name__)

'''NOTE: Indeed RSS blocks non-US IPs. Returns 0 results in production.
Kept as a demonstration of multi-source architecture.
Replace with Remotive or JSearch API for a second live source.'''

ROLE_QUERY_MAP: dict[Role, str] = {
    Role.ML_AI_ENGINEER: "AI engineer",
    Role.DATA_SCIENCE: "data scientist",
    Role.BACKEND_SWE: "backend engineer",
}

def _redact_secrets(message: str) -> str:
    """Adzuna authenticates via query params, and httpx exception messages
    include the full request URL — strip the credentials before logging."""
    return re.sub(r"(app_id|app_key)=[^&\s'\"]+", r"\1=***", message)


def _parse_indeed(query: str, limit: int) -> list[Job]:
    url = f"https://www.indeed.com/rss?q={query.replace(' ', '+')}&sort=date"
    feed = feedparser.parse(url)
    jobs = []

    for entry in feed.entries[:limit]:
        try:
            jobs.append(Job(
                title=entry.get("title", ""),
                company=entry.get("author", "Unknown"),
                location=entry.get("location", "Remote"),
                description=entry.get("summary", ""),
                url=entry.get("link", ""),
                posted_at=datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                          if hasattr(entry, "published_parsed") else None,
            ))
        except Exception as e:
            logger.warning(f"Skipped malformed Indeed entry: {e}")
            continue

    logger.info(f"Indeed returned {len(jobs)} jobs")
    return jobs


async def _fetch_adzuna(query: str, limit: int, location: str | None = None) -> list[Job]:
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_api_key,
        "results_per_page": limit,
        "what": query,
        "sort_by": "date",
    }
    if location:
        params["where"] = location

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.adzuna.com/v1/api/jobs/in/search/1",
            params=params,
        )
        response.raise_for_status()

    jobs = []
    for j in response.json().get("results", []):
        try:
            jobs.append(Job(
                title=j["title"],
                company=j.get("company", {}).get("display_name", "Unknown"),
                location=j.get("location", {}).get("display_name", "Remote"),
                description=j.get("description", ""),
                url=j["redirect_url"],
                posted_at=datetime.fromisoformat(j["created"])
                          if "created" in j else None,
            ))
        except Exception as e:
            logger.warning(f"Skipped malformed Adzuna entry: {e}")
            continue

    logger.info(f"Adzuna returned {len(jobs)} jobs")
    return jobs


def _deduplicate(jobs: list[Job], limit: int) -> list[Job]:
    seen = set()
    unique = []

    for job in jobs:
        key = (job.title.lower().strip(), job.company.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(job)

    return unique[:limit]


async def get_jobs(
    roles: list[Role] | None = None, location: str | None = None
) -> list[Job]:
    """Fetch postings for every role family in `roles` (None = all roles,
    ordered by preference). One Adzuna query per role, in parallel, with
    per-query failure isolation — one dead query must not kill the run."""
    if not roles:
        roles = list(Role)
    queries = [ROLE_QUERY_MAP[role] for role in roles]
    logger.info(f"Fetching jobs for roles={[r.value for r in roles]} -> queries={queries}")

    loop = asyncio.get_event_loop()

    # Indeed is the documented dead/demo path — one query is plenty.
    indeed_future = loop.run_in_executor(
        None, _parse_indeed, queries[0], settings.jobs_per_run
    )
    adzuna_futures = [
        _fetch_adzuna(query, settings.jobs_per_run, location) for query in queries
    ]

    results = await asyncio.gather(
        indeed_future,
        *adzuna_futures,
        return_exceptions=True,
    )
    indeed_jobs, adzuna_results = results[0], results[1:]

    combined = []

    if isinstance(indeed_jobs, Exception):
        logger.error(f"Indeed scrape failed: {indeed_jobs}")
    else:
        combined.extend(indeed_jobs)

    for query, adzuna_jobs in zip(queries, adzuna_results):
        if isinstance(adzuna_jobs, Exception):
            logger.error(
                f"Adzuna fetch failed for {query!r}: "
                f"{_redact_secrets(str(adzuna_jobs))}"
            )
        else:
            combined.extend(adzuna_jobs)

    # Filter out already-seen jobs before capping to jobs_per_run, so a run
    # doesn't get truncated down to postings that turn out to all be stale.
    deduped = _deduplicate(combined, limit=len(combined))
    unseen = filter_unseen(deduped)
    result = unseen[: settings.jobs_per_run]
    logger.info(
        f"Fetched {len(combined)} job(s): {len(deduped)} unique, "
        f"{len(deduped) - len(unseen)} already seen in a previous run, "
        f"{len(result)} new to process"
    )
    return result