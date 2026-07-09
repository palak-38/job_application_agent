# Job Hunter — a scheduled job-application pipeline

[![CI](https://github.com/palak-38/job_application_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/palak-38/job_application_agent/actions/workflows/ci.yml)
[![Daily digest](https://github.com/palak-38/job_application_agent/actions/workflows/daily-digest.yml/badge.svg)](https://github.com/palak-38/job_application_agent/actions/workflows/daily-digest.yml)
**Live:** [job-application-agent-1-f61g.onrender.com](https://job-application-agent-1-f61g.onrender.com)

A FastAPI backend that runs unattended twice a day: it discovers fresh job postings from the Adzuna API, has an LLM score each one against role-specific rubrics, and — only for postings that clear a threshold — surgically tailors my resume and emails me a digest with the tailored PDFs attached. Postings are never processed twice, runs are idempotent, and nothing is ever auto-submitted: I review and apply myself.

It is **not an agent** — it's a pipeline with exactly one model-driven control-flow decision (the scoring gate). The scoring call is a *quality filter and scaling guardrail*, not a cost saving, at the current volume of ~15 postings/day.

## How it works

```
GitHub Actions cron (2×/day)              manual: POST /api/v1/run {role?, threshold?, location?}
        │                                            │  (X-API-Key)
        ▼                                            ▼
┌─ FastAPI on Render ───────────────────────────────────────────────────┐
│  fetch (Adzuna, one query per role family, parallel)                  │
│    → dedup vs Turso (never re-process a posting; survives restarts)   │
│    → score: LLM rates each job against EVERY role rubric (0-10 +      │
│      reason + fresher-experience check); best score gates             │
│    → tailor (matched jobs only): LLM returns a validated JSON edit    │
│      set over the structured resume — summary + ≤6 bullet edits,      │
│      never invented facts, never a full rewrite                       │
│    → render fixed-template PDF (fpdf2, in memory)                     │
│    → email digest via Resend API (score + reason for every job,       │
│      skipped ones visibly listed)                                     │
│    → mark seen + record run history (shown at /)                      │
└───────────────────────────────────────────────────────────────────────┘
```

Layered: `routes → services → integrations → models`. One `Role` enum threads through all role-dependent behavior — search query, scoring rubric, and resume profile are all dicts keyed by the same value, so an unsupported role is a 422 at the API boundary, not a runtime surprise.

## Design decisions worth explaining

- **Role-keyed everything, best-role matching.** I apply to three role families (ML/AI, data science, backend). A scheduled run fetches and scores against *all* of them and keeps a posting if it fits *any* — a backend-flavored ML job shouldn't die because it scored low on one rubric. Ties go to my preference order.
- **Surgical resume edits, not regeneration.** Early versions asked the LLM to rewrite the whole resume; the output read as generic LLM prose and lost all structure. Now the resume is parsed into structured data, the model returns an indexed edit set (validated, out-of-range edits dropped), and a fixed PDF template does the layout. If tailoring output is unparseable after a retry, the original resume ships — a matched job never goes without an attachment.
- **SQLite → Turso, forced by deployment.** Dedup started as stdlib SQLite. Render's free tier has an ephemeral filesystem, which would wipe the DB on every restart and re-spam the digest — so production uses Turso (hosted libSQL). Same SQL dialect, so local dev and tests still run on plain sqlite3 with zero setup.
- **SMTP → Resend, forced by deployment.** Render's free tier blocks all outbound SMTP ports. The digest goes out as one HTTPS call to the Resend API in production; Gmail SMTP remains the local fallback.
- **Scheduler = GitHub Actions cron hitting `/run`**, not in-process APScheduler: the workflow log doubles as run observability, failures trigger GitHub's failure emails for free, and the free web instance is allowed to sleep between runs.
- **API over scraping.** Official Adzuna API only. A dead Indeed-RSS path is kept, honestly commented, as a demonstration of the multi-source design — it returns nothing outside US IPs.

## API

```bash
# scheduled semantics: all roles, server-side defaults
curl -X POST $URL/api/v1/run -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d '{}'

# restrict to one role family, override the gate threshold
curl -X POST $URL/api/v1/run -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" \
     -d '{"role": "backend_swe", "threshold": 7}'
```

`GET /` landing page + run history · `GET /runs` history as JSON · `GET /api/v1/health` · `GET /docs` interactive docs. `POST /api/v1/run` returns `{status, jobs_scored, jobs_matched, jobs_skipped}` and requires the `X-API-Key` header (it triggers LLM calls and email — not public).

## Running it yourself

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in the values below
uvicorn app.main:app --reload
python -m pytest app/tests  # 79 tests, no network required
```

| Env var | Purpose | Required |
|---|---|---|
| `GROQ_API_KEY` | LLM scoring + tailoring (Groq) | yes |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | job discovery | yes |
| `GOOGLE_RESUME_DOC_ID` | master resume Google Doc | yes |
| `SERVICE_ACCOUNT_FILE` / `GOOGLE_SERVICE_ACCOUNT_JSON` | Drive read-only credentials (file locally, JSON content on hosts) | yes (one) |
| `SENDER_EMAIL` / `GMAIL_APP_PASSWORD` / `RECIPIENT_EMAIL` | digest delivery | yes |
| `RESEND_API_KEY` | HTTPS email path (required on Render — SMTP blocked) | deploy |
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | persistent dedup + run history (local sqlite when unset) | deploy |
| `RUN_TOKEN` | X-API-Key guard on `/run` (open when unset) | deploy |
| `GROQ_MODEL`, `SCORE_THRESHOLD`, `DEFAULT_ROLE`, `JOBS_PER_RUN`, `CANDIDATE_EXPERIENCE`, `ROLE_RESUME_DOC_IDS` | tuning, all defaulted | no |

Deploying: `render.yaml` is a ready Render blueprint; set the env vars in the dashboard, add `APP_URL` + `RUN_TOKEN` as GitHub repo secrets, and the `daily-digest` workflow does the rest.

## Limitations

- **Human-in-the-loop by design** — it prepares applications; it never submits them.
- Per-job tailoring runs sequentially; no concurrency claims until that's built and measured.
- Scoring quality is bounded by the rubric text and the model; the threshold (default 6) is a tuning knob, not a guarantee.
- The Google Doc resume must keep light formatting conventions (ALL-CAPS section headers, `- ` bullets) to parse cleanly — styling itself doesn't survive Drive's plain-text export.
