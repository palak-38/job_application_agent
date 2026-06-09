import logging
from datetime import date
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.integrations.google_client import build_google_services
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def create_resume_doc(resume_text: str, job: Job) -> str:
    services = build_google_services(settings.service_account_file)
    docs = services["docs"]
    drive = services["drive"]

    title = f"Resume — {job.company} — {job.title} — {date.today()}"

    try:
        logger.info("Creating Google Doc")
        doc = docs.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        logger.info(f"Google Doc created: {doc_id}")

        logger.info("Inserting resume text")
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

        logger.info("Sharing Google Doc with recipient")
        drive.permissions().create(
            fileId=doc_id,
            body={
                "type": "user",
                "role": "reader",
                "emailAddress": settings.recipient_email,
            },
            sendNotificationEmail=False,
        ).execute()

        url = f"https://docs.google.com/document/d/{doc_id}/edit"
        logger.info(f"Created doc for {job.company} — {job.title}: {url}")
        return url

    except HttpError as e:
        logger.error(f"Google API failed at doc creation flow: {e}")
        logger.error(f"Status: {e.resp.status}")
        logger.error(f"Reason: {e.reason}")
        logger.error(f"Content: {e.content.decode('utf-8') if e.content else 'No content'}")
        raise