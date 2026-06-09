import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.models.schemas import RewrittenResume

logger = logging.getLogger(__name__)


def send_summary_email(results: list[RewrittenResume]) -> None:
    rows = "".join(
    f"""<tr>
        <td style='padding:8px;border:1px solid #ddd'>{r.job.company}</td>
        <td style='padding:8px;border:1px solid #ddd'>{r.job.title}</td>
        <td style='padding:8px;border:1px solid #ddd'>
            <a href='{r.job.url}'>Apply</a>
        </td>
    </tr>
    <tr>
        <td colspan='3' style='padding:12px;border:1px solid #ddd'>
            <pre style='white-space:pre-wrap;font-family:Arial'>{r.resume_text}</pre>
        </td>
    </tr>"""
    for r in results
)

    html = f"""
    <html>
    <body style='font-family:sans-serif;padding:20px'>
        <h2>Job Hunter — {date.today()}</h2>
        <p>{len(results)} matches today</p>
        <table style='border-collapse:collapse;width:100%'>
            <tr style='background:#f0f0f0'>
                <th style='padding:8px;border:1px solid #ddd'>Company</th>
                <th style='padding:8px;border:1px solid #ddd'>Role</th>
                <th style='padding:8px;border:1px solid #ddd'>Job Link</th>
                <th style='padding:8px;border:1px solid #ddd'>Resume</th>
            </tr>
            {rows}
        </table>
    </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Hunter — {len(results)} matches — {date.today()}"
    msg["From"]    = settings.sender_email
    msg["To"]      = settings.recipient_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.sender_email, settings.gmail_app_password)
        server.send_message(msg)

    logger.info(f"Digest email sent to {settings.recipient_email}")