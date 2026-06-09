import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents"
]


def build_google_services(service_account_file: str) -> dict:
    creds = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=SCOPES,
    )
    services = {
        "drive": build("drive", "v3", credentials=creds),
        "docs":  build("docs",  "v1", credentials=creds),
        "gmail": build("gmail", "v1", credentials=creds),
    }
    logger.info("Google API services built successfully")
    return services