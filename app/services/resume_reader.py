import io
import logging

from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.integrations.google_client import build_google_services

logger = logging.getLogger(__name__)


def read_resume_as_text() -> str:
    services = build_google_services(r"C:\Users\hp\Desktop\work\job_application_agent\service_account.json")
    drive = services["drive"]

    request = drive.files().export_media(
        fileId=settings.google_resume_doc_id,
        mimeType="text/plain",
    )

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    text = buffer.getvalue().decode("utf-8")
    logger.info(f"Resume loaded: {len(text)} characters")
    return text