from unittest.mock import MagicMock, patch

from app.models.schemas import Job, ScoredJob
from app.services.doc_creator import create_resume_pdf
from app.services.mailer import send_summary_email


def make_test_job(n: int = 1, company: str = "Acme Corp") -> Job:
    return Job(
        title="Software Engineer",
        company=company,
        location="Remote",
        description="Python developer needed",
        url=f"https://example.com/job/{n}",
    )


def send_with_mock_smtp(scored, attachments, threshold=6.0):
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        send_summary_email(scored, attachments, threshold=threshold)
    return mock_server


def test_create_resume_pdf_returns_pdf_bytes():
    pdf_bytes = create_resume_pdf("Resume text here", make_test_job())

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_create_resume_pdf_handles_unicode_punctuation():
    """LLM-rewritten resume text commonly contains em dashes, curly quotes,
    bullets, and ellipses, which the core Helvetica font can't encode and
    would otherwise crash rendering (FPDFUnicodeEncodingException)."""
    text = "Built a service — used Python, FastAPI • deployed with Docker … “smart quotes” and ‘these’"

    pdf_bytes = create_resume_pdf(text, make_test_job())

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_send_email_attaches_pdf_only_for_matched_jobs():
    scored = [
        ScoredJob(
            job=make_test_job(1, "Acme Corp"),
            score=8,
            reason="Strong Python/FastAPI overlap",
            resume_text="Rewritten resume",
        ),
        ScoredJob(
            job=make_test_job(2, "Bland Inc"),
            score=3,
            reason="Frontend-heavy role",
        ),
    ]
    attachments = [create_resume_pdf("Rewritten resume", scored[0].job)]

    mock_server = send_with_mock_smtp(scored, attachments)

    mock_server.login.assert_called_once()
    sent_msg = mock_server.send_message.call_args.args[0]
    attachment_parts = [
        part
        for part in sent_msg.walk()
        if part.get_content_disposition() == "attachment"
    ]
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "resume_Acme_Corp.pdf"


def test_digest_shows_scores_and_visibly_skipped_section():
    scored = [
        ScoredJob(
            job=make_test_job(1, "Acme Corp"),
            score=8,
            reason="Strong Python/FastAPI overlap",
            resume_text="Rewritten resume",
        ),
        ScoredJob(
            job=make_test_job(2, "Bland Inc"),
            score=3,
            reason="Frontend-heavy role",
        ),
        ScoredJob(
            job=make_test_job(3, "Mystery Ltd"),
            score=None,
            reason="scoring unavailable (unparseable model output)",
        ),
    ]
    attachments = [b"%PDF fake"]

    mock_server = send_with_mock_smtp(scored, attachments, threshold=6.0)

    sent_msg = mock_server.send_message.call_args.args[0]
    assert sent_msg["Subject"].startswith("Job Hunter — 1 matched / 3 scored")

    html = next(
        part.get_payload(decode=True).decode()
        for part in sent_msg.walk()
        if part.get_content_type() == "text/html"
    )
    assert "Matched" in html and "Skipped" in html
    assert "8/10" in html and "3/10" in html and "n/a" in html
    assert "Strong Python/FastAPI overlap" in html
    assert "Frontend-heavy role" in html


def test_digest_with_no_matches_still_sends_with_skipped_jobs():
    scored = [
        ScoredJob(
            job=make_test_job(1, "Bland Inc"),
            score=2,
            reason="Irrelevant stack",
        )
    ]

    mock_server = send_with_mock_smtp(scored, attachments=[])

    sent_msg = mock_server.send_message.call_args.args[0]
    assert sent_msg["Subject"].startswith("Job Hunter — 0 matched / 1 scored")
    html = next(
        part.get_payload(decode=True).decode()
        for part in sent_msg.walk()
        if part.get_content_type() == "text/html"
    )
    assert "No jobs passed the scoring gate" in html
    assert "Skipped" in html
