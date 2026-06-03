from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from app.api.routes import health, jobs  

logging.basicConfig(level=logging.INFO)  

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: runs before the server starts accepting requests
    print("Job Hunter API starting up")
    yield
    # shutdown: runs when the server is stopping
    print("Job Hunter API shutting down")


app = FastAPI(
    title="Job Hunter API",
    version="0.1.0",
    description="Scrapes jobs, rewrites resumes with an LLM, delivers a daily digest.",
    lifespan=lifespan,
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")