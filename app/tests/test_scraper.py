from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Job, Role
from app.services.job_scraper import ROLE_QUERY_MAP, _deduplicate, get_jobs


def make_job(title: str, company: str, n: int = 1) -> Job:
    return Job(
        title=title,
        company=company,
        location="Remote",
        description="Test description",
        url=f"https://example.com/job/{n}",
    )


def test_dedup_removes_identical_jobs():
    jobs = [
        make_job("Software Engineer", "Acme", 1),
        make_job("Software Engineer", "Acme", 2),
    ]
    result = _deduplicate(jobs, limit=10)
    assert len(result) == 1


def test_role_query_map_covers_every_role():
    for role in Role:
        assert isinstance(ROLE_QUERY_MAP[role], str) and ROLE_QUERY_MAP[role]


@pytest.mark.asyncio
async def test_get_jobs_threads_role_into_query():
    with patch(
        "app.services.job_scraper._fetch_adzuna", new_callable=AsyncMock
    ) as mock_adzuna, patch(
        "app.services.job_scraper._parse_indeed", return_value=[]
    ) as mock_indeed, patch(
        "app.services.job_scraper.filter_unseen", side_effect=lambda jobs: jobs
    ):
        mock_adzuna.return_value = []

        await get_jobs(role=Role.BACKEND_SWE)

        expected_query = ROLE_QUERY_MAP[Role.BACKEND_SWE]
        mock_adzuna.assert_awaited_once()
        assert mock_adzuna.call_args.args[0] == expected_query
        mock_indeed.assert_called_once()
        assert mock_indeed.call_args.args[0] == expected_query


@pytest.mark.asyncio
async def test_get_jobs_filters_seen_before_truncating():
    """A job beyond the jobs_per_run cutoff must still surface if the jobs
    ahead of it in the raw fetch order are all already-seen (F3 + F2 combined:
    truncation must not happen before dedup, or a run can silently return 0
    new jobs while unseen postings exist further down the list)."""
    jobs = [make_job(f"Role {i}", f"Company {i}", i) for i in range(6)]
    seen_urls = {str(j.url) for j in jobs[:5]}

    with patch(
        "app.services.job_scraper._fetch_adzuna", new_callable=AsyncMock
    ) as mock_adzuna, patch(
        "app.services.job_scraper._parse_indeed", return_value=jobs
    ), patch(
        "app.services.job_scraper.filter_unseen",
        side_effect=lambda js: [j for j in js if str(j.url) not in seen_urls],
    ), patch(
        "app.services.job_scraper.settings.jobs_per_run", 5
    ):
        mock_adzuna.return_value = []

        result = await get_jobs(role=Role.BACKEND_SWE)

    assert [j.title for j in result] == ["Role 5"]


def test_dedup_respects_limit():
    jobs = [make_job(f"Role {i}", f"Company {i}", i) for i in range(5)]
    result = _deduplicate(jobs, limit=3)
    assert len(result) == 3


def test_dedup_empty_list():
    result = _deduplicate([], limit=5)
    assert result == []


def test_dedup_case_insensitive():
    jobs = [
        make_job("software engineer", "acme corp", 1),
        make_job("Software Engineer", "Acme Corp", 2),
    ]
    result = _deduplicate(jobs, limit=10)
    assert len(result) == 1