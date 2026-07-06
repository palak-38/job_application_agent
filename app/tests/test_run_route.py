from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Role, RunCounts

client = TestClient(app)

COUNTS = RunCounts(jobs_scored=5, jobs_matched=3, jobs_skipped=2)


@patch("app.api.routes.run.run_private_pipeline", new_callable=AsyncMock)
def test_run_with_explicit_role(mock_pipeline):
    mock_pipeline.return_value = COUNTS

    resp = client.post("/api/v1/run", json={"role": "data_science"})

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "email_sent",
        "jobs_scored": 5,
        "jobs_matched": 3,
        "jobs_skipped": 2,
    }
    mock_pipeline.assert_awaited_once_with(
        role=Role.DATA_SCIENCE, location=None, threshold=None
    )


@patch("app.api.routes.run.run_private_pipeline", new_callable=AsyncMock)
def test_run_falls_back_to_default_role_when_body_empty(mock_pipeline):
    mock_pipeline.return_value = COUNTS

    resp = client.post("/api/v1/run", json={})

    assert resp.status_code == 200
    mock_pipeline.assert_awaited_once_with(
        role=Role.ML_AI_ENGINEER, location=None, threshold=None
    )


@patch("app.api.routes.run.run_private_pipeline", new_callable=AsyncMock)
def test_run_threads_caller_threshold_through(mock_pipeline):
    mock_pipeline.return_value = COUNTS

    resp = client.post("/api/v1/run", json={"threshold": 7.5})

    assert resp.status_code == 200
    mock_pipeline.assert_awaited_once_with(
        role=Role.ML_AI_ENGINEER, location=None, threshold=7.5
    )


def test_run_rejects_invalid_role():
    resp = client.post("/api/v1/run", json={"role": "not_a_real_role"})

    assert resp.status_code == 422


def test_run_rejects_out_of_range_threshold():
    assert client.post("/api/v1/run", json={"threshold": 15}).status_code == 422
    assert client.post("/api/v1/run", json={"threshold": -1}).status_code == 422
