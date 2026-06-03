from app.models.schemas import Job
from app.services.job_scraper import _deduplicate


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