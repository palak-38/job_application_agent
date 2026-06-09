from unittest.mock import MagicMock, patch
from app.services.doc_creator import create_resume_doc
from app.services.mailer import send_summary_email
from app.models.schemas import Job, RewrittenResume


def make_test_job() -> Job:
    return Job(
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        description="Python developer needed",
        url="https://example.com/job/1",
    )


def test_create_resume_doc_returns_url():
    with patch("app.services.doc_creator.build_google_services") as mock_build:
        mock_docs  = MagicMock()
        mock_drive = MagicMock()

        mock_docs.documents().create().execute.return_value = {
            "documentId": "fake_doc_id_123"
        }

        mock_build.return_value = {
            "docs":  mock_docs,
            "drive": mock_drive,
        }

        result = create_resume_doc("Resume text here", make_test_job())

    assert result == "https://docs.google.com/document/d/fake_doc_id_123/edit"


def test_create_resume_doc_sets_permissions():
    with patch("app.services.doc_creator.build_google_services") as mock_build:
        mock_docs  = MagicMock()
        mock_drive = MagicMock()

        mock_docs.documents().create().execute.return_value = {
            "documentId": "fake_doc_id_123"
        }

        mock_build.return_value = {
            "docs":  mock_docs,
            "drive": mock_drive,
        }

        create_resume_doc("Resume text here", make_test_job())

    mock_drive.permissions().create.assert_called_once()
    call_kwargs = mock_drive.permissions().create.call_args.kwargs
    assert call_kwargs["body"]["type"] == "anyone"
    assert call_kwargs["body"]["role"] == "reader"


def test_send_email_calls_smtp():
    results = [
        RewrittenResume(
            job=make_test_job(),
            resume_text="Rewritten resume",
            doc_url="https://docs.google.com/document/d/abc/edit",
        )
    ]

    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send_summary_email(results)

    mock_server.login.assert_called_once()
    mock_server.send_message.assert_called_once()