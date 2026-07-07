import json
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import settings

logger = logging.getLogger(__name__)

# Least privilege: Google is used only to READ the master resume. No Docs
# API, no Drive-write, no Gmail (email goes out via SMTP).
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def build_drive_service():
    if settings.google_service_account_json:
        # Deployed: the service-account JSON is env-var content, not a file.
        info = json.loads(settings.google_service_account_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        source = "env var"
    else:
        creds = service_account.Credentials.from_service_account_file(
            settings.service_account_file, scopes=SCOPES
        )
        source = "file"

    logger.info(f"Google Drive service built (credentials from {source})")
    return build("drive", "v3", credentials=creds)
