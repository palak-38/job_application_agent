import logging
from datetime import date

from googleapiclient.errors import HttpError

from app.core.config import settings
from app.integrations.google_client import build_google_services
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def create_resume_doc(resume_text: str, job: Job) -> str:
    if not settings.google_output_folder_id:
        raise ValueError("GOOGLE_OUTPUT_FOLDER_ID is missing")

    services = build_google_services(settings.service_account_file)
    docs = services["docs"]
    drive = services["drive"]

    title = f"Resume — {job.company} — {job.title} — {date.today()}"

    try:
        logger.info("Creating Google Doc inside shared output folder")

        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [settings.google_output_folder_id],
        }

        created_file = drive.files().create(
            body=file_metadata,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()

        doc_id = created_file["id"]
        logger.info(f"Google Doc created: {doc_id}")

        logger.info("Inserting rewritten resume text")
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": resume_text,
                        }
                    }
                ]
            },
        ).execute()

        url = created_file.get("webViewLink") or f"https://docs.google.com/document/d/{doc_id}/edit"

        logger.info(f"Created resume doc for {job.company} — {job.title}: {url}")
        return url

    except HttpError as e:
        logger.error("Google API failed while creating resume doc")
        logger.error(f"Status: {e.resp.status}")
        logger.error(f"Reason: {e.reason}")
        logger.error(f"Content: {e.content.decode('utf-8') if e.content else 'No content'}")
        raise