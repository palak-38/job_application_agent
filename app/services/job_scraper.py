import asyncio
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from app.core.config import settings
from app.core.store import filter_unseen
from app.models.schemas import Job

logger = logging.getLogger(__name__)

'''NOTE: Indeed RSS blocks non-US IPs. Returns 0 results in production.
Kept as a demonstration of multi-source architecture.
Replace with Remotive or JSearch API for a second live source.'''

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


async def _fetch_adzuna(query: str, limit: int) -> list[Job]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.adzuna.com/v1/api/jobs/in/search/1",
            params={
                "app_id": settings.adzuna_app_id,
                "app_key": settings.adzuna_api_key,
                "results_per_page": limit,
                "what": query,
                "sort_by": "date",
            },
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


async def get_jobs() -> list[Job]:
    loop = asyncio.get_event_loop()

    indeed_future = loop.run_in_executor(
        None, _parse_indeed, settings.job_query, settings.jobs_per_run
    )
    adzuna_future = _fetch_adzuna(settings.job_query, settings.jobs_per_run)

    indeed_jobs, adzuna_jobs = await asyncio.gather(
        indeed_future,
        adzuna_future,
        return_exceptions=True,
    )

    combined = []

    if isinstance(indeed_jobs, Exception):
        logger.error(f"Indeed scrape failed: {indeed_jobs}")
    else:
        combined.extend(indeed_jobs)

    if isinstance(adzuna_jobs, Exception):
        logger.error(f"Adzuna fetch failed: {adzuna_jobs}")
    else:
        combined.extend(adzuna_jobs)

    unique = _deduplicate(combined, settings.jobs_per_run)
    result = filter_unseen(unique)
    logger.info(f"Pipeline will process {len(result)} new job(s)")
    return result