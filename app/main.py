from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Job Agent API",
    description="Automated job hunting assistant",
    version="0.1.0"
)

class HealthResponse(BaseModel):
    status: str
    version: str

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version="0.1.0")

@app.get("/")
async def root():
    return {"message": "Visit /docs to explore the API"}