from app.core.store import filter_unseen, mark_seen
from app.models.schemas import Job


def make_job(n: int) -> Job:
    return Job(
        title=f"Role {n}",
        company=f"Company {n}",
        location="Remote",
        description="desc",
        url=f"https://example.com/job/{n}",
    )


def test_filter_unseen_returns_all_on_fresh_db(tmp_path):
    db = str(tmp_path / "seen.db")
    jobs = [make_job(1), make_job(2)]

    assert filter_unseen(jobs, db_path=db) == jobs


def test_seen_jobs_are_skipped_on_next_run(tmp_path):
    db = str(tmp_path / "seen.db")
    jobs = [make_job(1), make_job(2)]

    mark_seen(jobs, db_path=db)

    # A second run the same day processes zero already-seen jobs (F3).
    assert filter_unseen(jobs, db_path=db) == []


def test_only_new_jobs_survive(tmp_path):
    db = str(tmp_path / "seen.db")

    mark_seen([make_job(1)], db_path=db)

    new_job = make_job(2)
    assert filter_unseen([make_job(1), new_job], db_path=db) == [new_job]


def test_mark_seen_is_idempotent(tmp_path):
    db = str(tmp_path / "seen.db")
    jobs = [make_job(1)]

    mark_seen(jobs, db_path=db)
    mark_seen(jobs, db_path=db)  # duplicate URL must not raise

    assert filter_unseen(jobs, db_path=db) == []
