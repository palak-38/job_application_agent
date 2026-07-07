from unittest.mock import MagicMock, patch

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


def test_filter_unseen_uses_one_query_for_all_urls(tmp_path):
    """With a hosted backend every statement is a network round-trip, so
    lookups must be a single IN query, not one SELECT per job (N+1)."""
    db = str(tmp_path / "seen.db")
    mark_seen([make_job(1)], db_path=db)
    jobs = [make_job(n) for n in range(1, 6)]

    with patch("app.core.store.sqlite3.connect", wraps=__import__("sqlite3").connect) as spy:
        filter_unseen(jobs, db_path=db)
        conn_calls = spy.call_count

    assert conn_calls == 1  # one connection, and inside it one SELECT


def test_turso_backend_selected_when_url_configured():
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = []
    mock_libsql = MagicMock()
    mock_libsql.connect.return_value = mock_conn

    with patch.dict("sys.modules", {"libsql": mock_libsql}), patch(
        "app.core.store.settings.turso_database_url", "libsql://test-db.turso.io"
    ), patch("app.core.store.settings.turso_auth_token", "tok"):
        result = filter_unseen([make_job(1)])

    mock_libsql.connect.assert_called_once_with(
        "libsql://test-db.turso.io", auth_token="tok"
    )
    mock_conn.commit.assert_called_once()
    assert len(result) == 1


def test_explicit_db_path_always_means_local_sqlite(tmp_path):
    """Tests and local tooling that pass db_path must never touch Turso,
    even when Turso settings are present in the environment."""
    db = str(tmp_path / "seen.db")
    mock_libsql = MagicMock()

    with patch.dict("sys.modules", {"libsql": mock_libsql}), patch(
        "app.core.store.settings.turso_database_url", "libsql://test-db.turso.io"
    ):
        assert filter_unseen([make_job(1)], db_path=db) == [make_job(1)]

    mock_libsql.connect.assert_not_called()
