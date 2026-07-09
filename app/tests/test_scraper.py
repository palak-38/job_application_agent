import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import Job, Role
from app.services.job_scraper import (
    ROLE_QUERY_MAP,
    _deduplicate,
    _redact_secrets,
    get_jobs,
)


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
async def test_get_jobs_threads_single_role_into_query():
    with patch(
        "app.services.job_scraper._fetch_adzuna", new_callable=AsyncMock
    ) as mock_adzuna, patch(
        "app.services.job_scraper._parse_indeed", return_value=[]
    ) as mock_indeed, patch(
        "app.services.job_scraper.filter_unseen", side_effect=lambda jobs: jobs
    ):
        mock_adzuna.return_value = []

        await get_jobs(roles=[Role.BACKEND_SWE])

        expected_query = ROLE_QUERY_MAP[Role.BACKEND_SWE]
        mock_adzuna.assert_awaited_once()
        assert mock_adzuna.call_args.args[0] == expected_query
        mock_indeed.assert_called_once()
        assert mock_indeed.call_args.args[0] == expected_query


@pytest.mark.asyncio
async def test_get_jobs_fetches_every_role_when_unrestricted():
    """roles=None means the scheduled 'match anything I could do' run:
    one Adzuna query per role family, combined."""
    with patch(
        "app.services.job_scraper._fetch_adzuna", new_callable=AsyncMock
    ) as mock_adzuna, patch(
        "app.services.job_scraper._parse_indeed", return_value=[]
    ), patch(
        "app.services.job_scraper.filter_unseen", side_effect=lambda jobs: jobs
    ):
        mock_adzuna.return_value = []

        await get_jobs()

        queried = {call.args[0] for call in mock_adzuna.await_args_list}
        assert queried == {ROLE_QUERY_MAP[role] for role in Role}


@pytest.mark.asyncio
async def test_one_failing_role_query_does_not_kill_the_run():
    ok_job = make_job("Backend Engineer", "Acme", 1)

    async def adzuna_side_effect(query, limit, location=None):
        if query == ROLE_QUERY_MAP[Role.ML_AI_ENGINEER]:
            raise Exception("boom")
        return [ok_job] if query == ROLE_QUERY_MAP[Role.BACKEND_SWE] else []

    with patch(
        "app.services.job_scraper._fetch_adzuna", side_effect=adzuna_side_effect
    ), patch(
        "app.services.job_scraper._parse_indeed", return_value=[]
    ), patch(
        "app.services.job_scraper.filter_unseen", side_effect=lambda jobs: jobs
    ):
        result = await get_jobs()

    assert result == [ok_job]


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

        result = await get_jobs(roles=[Role.BACKEND_SWE])

    assert [j.title for j in result] == ["Role 5"]


def test_redact_secrets_strips_adzuna_credentials():
    message = (
        "Client error '401 Unauthorized' for url 'https://api.adzuna.com/v1/"
        "api/jobs/in/search/1?app_id=abc123&app_key=deadbeef99&what=AI+engineer'"
    )
    redacted = _redact_secrets(message)
    assert "abc123" not in redacted
    assert "deadbeef99" not in redacted
    assert "app_id=***" in redacted and "app_key=***" in redacted
    assert "what=AI+engineer" in redacted  # non-secret params survive


@pytest.mark.asyncio
async def test_adzuna_failure_logged_without_secrets(caplog):
    """httpx exception messages embed the full request URL, which carries
    the Adzuna credentials as query params — the error log must not."""
    error = Exception(
        "error for url 'https://api.adzuna.com/...?app_id=abc123&app_key=deadbeef99'"
    )
    with patch(
        "app.services.job_scraper._fetch_adzuna", new_callable=AsyncMock,
        side_effect=error,
    ), patch(
        "app.services.job_scraper._parse_indeed", return_value=[]
    ), patch(
        "app.services.job_scraper.filter_unseen", side_effect=lambda jobs: jobs
    ), caplog.at_level(logging.ERROR):
        result = await get_jobs(roles=[Role.ML_AI_ENGINEER])

    assert result == []
    assert "Adzuna fetch failed" in caplog.text
    assert "deadbeef99" not in caplog.text and "abc123" not in caplog.text


def test_httpx_request_logging_is_silenced():
    """httpx logs full request URLs at INFO (query-param secrets included);
    app startup must raise its logger to WARNING."""
    import app.main  # noqa: F401  (importing applies the logging config)

    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)


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