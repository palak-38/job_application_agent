from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Role

client = TestClient(app)


@patch("app.api.routes.run.run_private_pipeline", new_callable=AsyncMock)
def test_run_with_explicit_role(mock_pipeline):
    mock_pipeline.return_value = 3

    resp = client.post("/api/v1/run", json={"role": "data_science"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "email_sent", "jobs_processed": 3}
    mock_pipeline.assert_awaited_once_with(role=Role.DATA_SCIENCE, location=None)


@patch("app.api.routes.run.run_private_pipeline", new_callable=AsyncMock)
def test_run_falls_back_to_default_role_when_body_empty(mock_pipeline):
    mock_pipeline.return_value = 0

    resp = client.post("/api/v1/run", json={})

    assert resp.status_code == 200
    mock_pipeline.assert_awaited_once_with(role=Role.ML_AI_ENGINEER, location=None)


def test_run_rejects_invalid_role():
    resp = client.post("/api/v1/run", json={"role": "not_a_real_role"})

    assert resp.status_code == 422
