import logging
from datetime import date

from app.core.config import settings
from app.integrations.google_client import build_google_services
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def create_resume_doc(resume_text: str, job: Job) -> str:
    services = build_google_services(settings.service_account_file)
    docs  = services["docs"]
    drive = services["drive"]

    title = f"Resume — {job.company} — {job.title} — {date.today()}"

    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

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

    drive.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    logger.info(f"Created doc for {job.company} — {job.title}: {url}")
    return url