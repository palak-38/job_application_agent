import base64
import logging
import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.config import settings
from app.models.schemas import ScoredJob

logger = logging.getLogger(__name__)

_CELL = "padding:8px;border:1px solid #ddd"


def _attachment_filename(s: ScoredJob) -> str:
    safe_company = "".join(c if c.isalnum() else "_" for c in s.job.company)
    return f"resume_{safe_company}.pdf"


def _score_cell(s: ScoredJob) -> str:
    return "n/a" if s.score is None else f"{s.score}/10"


def _matched_role_cell(s: ScoredJob) -> str:
    return s.matched_role.value if s.matched_role else "—"


def _rows(jobs: list[ScoredJob], with_attachment: bool) -> str:
    return "".join(
        f"""<tr>
        <td style='{_CELL}'>{s.job.company}</td>
        <td style='{_CELL}'>{s.job.title}</td>
        <td style='{_CELL}'>{_matched_role_cell(s)}</td>
        <td style='{_CELL}'>{_score_cell(s)}</td>
        <td style='{_CELL}'>{s.reason}</td>
        <td style='{_CELL}'><a href='{s.job.url}'>Apply</a></td>
        <td style='{_CELL}'>{_attachment_filename(s) if with_attachment else "—"}</td>
    </tr>"""
        for s in jobs
    )


def _table(jobs: list[ScoredJob], with_attachment: bool) -> str:
    return f"""<table style='border-collapse:collapse;width:100%'>
        <tr style='background:#f0f0f0'>
            <th style='{_CELL}'>Company</th>
            <th style='{_CELL}'>Role</th>
            <th style='{_CELL}'>Matched as</th>
            <th style='{_CELL}'>Score</th>
            <th style='{_CELL}'>Reason</th>
            <th style='{_CELL}'>Job Link</th>
            <th style='{_CELL}'>Attachment</th>
        </tr>
        {_rows(jobs, with_attachment)}
    </table>"""


def _build_digest_html(
    scored: list[ScoredJob],
    matched: list[ScoredJob],
    skipped: list[ScoredJob],
    threshold: float,
) -> str:
    matched_html = (
        f"<h3>Matched — resume attached ({len(matched)})</h3>"
        + _table(matched, with_attachment=True)
        if matched
        else "<h3>No jobs passed the scoring gate today.</h3>"
    )
    skipped_html = (
        f"<h3>Skipped — below threshold {threshold:g} ({len(skipped)})</h3>"
        "<p>Scored but not rewritten. 'n/a' means the score was unavailable "
        "(included for visibility, no resume generated).</p>"
        + _table(skipped, with_attachment=False)
        if skipped
        else ""
    )

    return f"""
    <html>
    <body style='font-family:sans-serif;padding:20px'>
        <h2>Job Hunter — {date.today()}</h2>
        <p>{len(scored)} new job(s) scored, {len(matched)} matched the
        scoring gate (threshold {threshold:g}). Tailored resumes are attached
        as PDFs.</p>
        {matched_html}
        {skipped_html}
    </body>
    </html>"""


def _send_via_resend(
    subject: str, html: str, attachments: list[tuple[str, bytes]]
) -> None:
    """HTTPS email path for deployed instances: Render's free tier blocks
    all outbound SMTP ports, so the digest goes out via the Resend API
    (plain HTTPS on 443) instead."""
    payload = {
        "from": settings.resend_from,
        "to": [settings.recipient_email],
        "subject": subject,
        "html": html,
        "attachments": [
            {"filename": name, "content": base64.b64encode(pdf).decode()}
            for name, pdf in attachments
        ],
    }
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    logger.info(
        f"Digest email sent to {settings.recipient_email} via Resend "
        f"(id={response.json().get('id', '?')})"
    )


def _send_via_smtp(
    subject: str, html: str, attachments: list[tuple[str, bytes]]
) -> None:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.sender_email
    msg["To"] = settings.recipient_email
    msg.attach(MIMEText(html, "html"))

    for filename, pdf_bytes in attachments:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.sender_email, settings.gmail_app_password)
        server.send_message(msg)

    logger.info(f"Digest email sent to {settings.recipient_email} via SMTP")


def send_summary_email(
    scored: list[ScoredJob], attachments: list[bytes], threshold: float
) -> None:
    """Send the daily digest. `attachments` aligns in order with the subset
    of `scored` that has resume_text (the matched jobs)."""
    matched = [s for s in scored if s.resume_text is not None]
    skipped = [s for s in scored if s.resume_text is None]

    subject = (
        f"Job Hunter — {len(matched)} matched / {len(scored)} scored — {date.today()}"
    )
    html = _build_digest_html(scored, matched, skipped, threshold)
    named_attachments = [
        (_attachment_filename(s), pdf) for s, pdf in zip(matched, attachments)
    ]

    if settings.resend_api_key:
        _send_via_resend(subject, html, named_attachments)
    else:
        _send_via_smtp(subject, html, named_attachments)

    logger.info(f"Digest summary: {len(matched)} matched, {len(skipped)} skipped")
