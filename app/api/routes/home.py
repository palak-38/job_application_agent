from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.store import recent_runs

router = APIRouter(tags=["home"])

_CELL = "padding:6px 10px;border:1px solid #e0e0e0;font-size:14px"


@router.get("/runs")
async def run_history(limit: int = 20):
    """Recent pipeline runs — public, read-only. Proof the scheduled runs
    actually happen."""
    return recent_runs(limit=min(limit, 50))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    rows = "".join(
        f"""<tr>
        <td style='{_CELL}'>{r["ran_at"]}</td>
        <td style='{_CELL}'>{r["requested_role"]}</td>
        <td style='{_CELL}'>{r["jobs_scored"]}</td>
        <td style='{_CELL}'>{r["jobs_matched"]}</td>
        <td style='{_CELL}'>{r["jobs_skipped"]}</td>
        <td style='{_CELL}'>{r["status"]}</td>
    </tr>"""
        for r in recent_runs(limit=10)
    )
    history = (
        f"""<table style='border-collapse:collapse;margin-top:8px'>
        <tr style='background:#f5f5f5'>
            <th style='{_CELL}'>Ran at (UTC)</th><th style='{_CELL}'>Role scope</th>
            <th style='{_CELL}'>Scored</th><th style='{_CELL}'>Matched</th>
            <th style='{_CELL}'>Skipped</th><th style='{_CELL}'>Status</th>
        </tr>{rows}</table>"""
        if rows
        else "<p><em>No runs recorded yet.</em></p>"
    )

    return f"""
    <html>
    <head><title>Job Hunter API</title></head>
    <body style='font-family:sans-serif;max-width:820px;margin:40px auto;padding:0 16px;color:#222'>
        <h1 style='margin-bottom:4px'>Job Hunter API</h1>
        <p style='color:#555;margin-top:0'>
            A scheduled job-application pipeline with one model-driven
            control-flow decision: an LLM scores each fresh posting against
            role-specific rubrics, and only worthwhile matches get a resume
            tailored (surgically, never fabricated) and emailed as a daily
            digest. Runs unattended twice a day via GitHub Actions cron.
        </p>
        <p>
            <a href='/docs'>Interactive API docs</a> ·
            <a href='/runs'>Run history (JSON)</a> ·
            <a href='https://github.com/palak-38/job_application_agent'>Source on GitHub</a>
        </p>
        <h2 style='font-size:18px'>Recent runs</h2>
        {history}
        <p style='color:#888;font-size:13px;margin-top:24px'>
            POST /api/v1/run requires an API key — triggering runs is not public.
        </p>
    </body>
    </html>"""
