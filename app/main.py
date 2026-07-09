from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from app.api.routes import health, home, jobs, run


logging.basicConfig(level=logging.INFO)

# httpx logs every request URL at INFO, and Adzuna authenticates via query
# params — so its app_id/app_key would land in the console/log output.
# Warnings and errors still come through.
logging.getLogger("httpx").setLevel(logging.WARNING)

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
app.include_router(run.router, prefix="/api/v1")
app.include_router(home.router)  # landing page at / and run history at /runs