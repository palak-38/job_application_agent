import json
from unittest.mock import MagicMock, patch

from app.integrations.google_client import SCOPES, build_drive_service


def test_scope_is_drive_readonly_only():
    """Least privilege (brief §8): Google is only ever used to READ the
    resume. No Docs API, no Drive-write, no Gmail scope."""
    assert SCOPES == ["https://www.googleapis.com/auth/drive.readonly"]


def test_credentials_from_env_var_when_set():
    fake_info = {"type": "service_account", "project_id": "test"}

    with patch(
        "app.integrations.google_client.settings.google_service_account_json",
        json.dumps(fake_info),
    ), patch(
        "app.integrations.google_client.service_account.Credentials"
    ) as mock_creds, patch(
        "app.integrations.google_client.build", return_value=MagicMock()
    ) as mock_build:
        build_drive_service()

    mock_creds.from_service_account_info.assert_called_once_with(
        fake_info, scopes=SCOPES
    )
    mock_creds.from_service_account_file.assert_not_called()
    mock_build.assert_called_once()
    assert mock_build.call_args.args[:2] == ("drive", "v3")


def test_credentials_from_file_when_env_var_unset():
    with patch(
        "app.integrations.google_client.settings.google_service_account_json", None
    ), patch(
        "app.integrations.google_client.settings.service_account_file", "sa.json"
    ), patch(
        "app.integrations.google_client.service_account.Credentials"
    ) as mock_creds, patch(
        "app.integrations.google_client.build", return_value=MagicMock()
    ):
        build_drive_service()

    mock_creds.from_service_account_file.assert_called_once_with(
        "sa.json", scopes=SCOPES
    )
    mock_creds.from_service_account_info.assert_not_called()
