import io
import logging

from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.integrations.google_client import build_drive_service
from app.models.schemas import Role

logger = logging.getLogger(__name__)


def read_resume_as_text(role: Role) -> str:
    # Profile-ready lookup: a role with its own doc id configured gets that
    # profile; everything else falls back to the master resume.
    doc_id = settings.role_resume_doc_ids.get(role, settings.google_resume_doc_id)
    profile = "per-role" if role in settings.role_resume_doc_ids else "master"
    logger.info(f"Loading {profile} resume for role={role.value}")

    drive = build_drive_service()

    request = drive.files().export_media(
        fileId=doc_id,
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