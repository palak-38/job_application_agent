from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FAKE_RUNS = [
    {
        "ran_at": "2026-07-08 01:30:00",
        "requested_role": "all",
        "jobs_scored": 5,
        "jobs_matched": 2,
        "jobs_skipped": 3,
        "status": "email_sent",
    }
]


@patch("app.api.routes.home.recent_runs", return_value=FAKE_RUNS)
def test_landing_page_shows_service_and_history(mock_runs):
    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Job Hunter API" in resp.text
    assert "/docs" in resp.text
    assert "email_sent" in resp.text  # run history rendered


@patch("app.api.routes.home.recent_runs", return_value=[])
def test_landing_page_handles_empty_history(mock_runs):
    resp = client.get("/")

    assert resp.status_code == 200
    assert "No runs recorded yet" in resp.text


@patch("app.api.routes.home.recent_runs", return_value=FAKE_RUNS)
def test_runs_endpoint_returns_json_history(mock_runs):
    resp = client.get("/runs")

    assert resp.status_code == 200
    assert resp.json() == FAKE_RUNS


@patch("app.api.routes.home.recent_runs", return_value=[])
def test_runs_endpoint_caps_limit(mock_runs):
    resp = client.get("/runs?limit=500")

    assert resp.status_code == 200
    mock_runs.assert_called_once_with(limit=50)
