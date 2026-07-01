from unittest.mock import MagicMock, patch

from app.models.schemas import Job, RewrittenResume
from app.services.doc_creator import create_resume_pdf
from app.services.mailer import send_summary_email


def make_test_job() -> Job:
    return Job(
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        description="Python developer needed",
        url="https://example.com/job/1",
    )


def test_create_resume_pdf_returns_pdf_bytes():
    pdf_bytes = create_resume_pdf("Resume text here", make_test_job())

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_send_email_attaches_pdf():
    results = [
        RewrittenResume(
            job=make_test_job(),
            resume_text="Rewritten resume",
        )
    ]
    attachments = [create_resume_pdf("Rewritten resume", make_test_job())]

    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send_summary_email(results, attachments)

    mock_server.login.assert_called_once()
    sent_msg = mock_server.send_message.call_args.args[0]
    attachment_parts = [
        part
        for part in sent_msg.walk()
        if part.get_content_disposition() == "attachment"
    ]
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "resume_Acme_Corp.pdf"
