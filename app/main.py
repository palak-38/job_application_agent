from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from app.routers import jobs

load_dotenv()

app = FastAPI(
    title="Job Agent API",
    description="Automated job hunting assistant",
    version="0.2.0"
)

app.include_router(jobs.router)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version="0.2.0")


@app.get("/")
async def root():
    return {"message": "Visit /docs to explore the API"}