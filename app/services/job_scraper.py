import asyncio
import os
import httpx
import feedparser
from typing import List
from app.models.job import Job
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "in")


async def fetch_indeed_jobs(query: str, location: str, limit: int = 5) -> List[Job]:
    url = f"https://www.indeed.com/rss?q={query}&l={location}&sort=date"
    feed = await asyncio.to_thread(feedparser.parse, url)

    jobs = []
    for entry in feed.entries[:limit]:
        jobs.append(Job(
            title=entry.get("title", ""),
            company=entry.get("source", {}).get("value", "Unknown"),
            location=location,
            url=entry.get("link", ""),
            description=entry.get("summary", ""),
            source="indeed",
            posted_date=entry.get("published", None),
        ))
    return jobs


async def fetch_adzuna_jobs(query: str, location: str, limit: int = 5) -> List[Job]:
    url = (
        f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
        f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
        f"&results_per_page={limit}&what={query}&where={location}&sort_by=date"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()

    jobs = []
    for result in data.get("results", []):
        jobs.append(Job(
            title=result.get("title", ""),
            company=result.get("company", {}).get("display_name", "Unknown"),
            location=result.get("location", {}).get("display_name", location),
            url=result.get("redirect_url", ""),
            description=result.get("description", ""),
            source="adzuna",
            posted_date=result.get("created", None),
        ))
    return jobs


async def fetch_jobs(query: str, location: str, limit: int = 5) -> List[Job]:
    jobs = []

    try:
        indeed_jobs = await fetch_indeed_jobs(query, location, limit)
        jobs.extend(indeed_jobs)
    except Exception as e:
        print(f"[WARNING] Indeed failed: {e}")

    try:
        adzuna_jobs = await fetch_adzuna_jobs(query, location, limit)
        jobs.extend(adzuna_jobs)
    except Exception as e:
        print(f"[WARNING] Adzuna failed: {e}")

    return jobs