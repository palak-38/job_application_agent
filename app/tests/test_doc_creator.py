from app.models.schemas import Job
from app.services.doc_creator import create_resume_doc

job = Job(
    title="Test Role",
    company="Test Company",
    location="Remote",
    description="Testing Google Doc creation",
    url="https://example.com/job/test",
)

url = create_resume_doc(
    "This is a test rewritten resume.\n\nSkills: Python, FastAPI, Automation.",
    job,
)

print(url)