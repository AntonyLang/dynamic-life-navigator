# Dynamic Life Navigator

Backend foundation for the Dynamic Life Navigator MVP.

## Current scope

This repository currently provides:

- FastAPI application bootstrap
- environment-based settings
- request ID middleware and basic logging
- `/health` and `/ready` endpoints
- PM-aligned API aliases for `/api/v1/events/ingest`, `/api/v1/state`, `/api/v1/recommendations/next`, `/api/v1/recommendations/{id}/feedback`, and `/api/v1/brief`
- Celery bootstrap
- local Docker Compose for PostgreSQL and Redis
- database-backed state updates, pull recommendations, feedback learning, and weak push decision records

`ENABLE_WORKER_DISPATCH` defaults to `false` so request handlers stay fast even when Redis/workers are not running locally.
`DEFAULT_USER_ID` is the single-user MVP identity used by the current DB-backed services.
The current push path only decides whether a push recommendation should be generated and stores the result in `recommendation_records`; it does not send external notifications yet.

## Local setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Copy `.env.example` to `.env` and adjust values if needed.
4. Start local dependencies:

```bash
docker compose up -d
```

## Run the API

```bash
uvicorn app.main:app --reload
```

## Run the worker

```bash
celery -A app.workers.celery_app:celery_app worker -l info
```

When `ENABLE_WORKER_DISPATCH=false`, HTTP ingest routes use an in-process FastAPI background pipeline for local development. That keeps the MVP event -> state -> recommendation loop moving even when Redis/Celery workers are not running.
When `ENABLE_WORKER_DISPATCH=true`, the real Celery path is used instead and the request handlers only emit the ack plus task dispatch.

On Windows, prefer the solo pool for local verification:

```powershell
$env:ENABLE_WORKER_DISPATCH='true'
celery -A app.workers.celery_app:celery_app worker -l info -P solo
```

## Run the frontend shell

The repository now includes a React + Vite thin client under `frontend/` for MVP integration work.

1. Keep the API running on `http://127.0.0.1:8000`.
2. Install frontend dependencies:

```powershell
cd frontend
npm.cmd install
```

3. Start the Vite dev server:

```powershell
cd frontend
npm.cmd run dev
```

The Vite proxy forwards `/api/*` to the local FastAPI server, so no extra CORS setup is required for local development.
That proxy-only behavior is local-dev convenience, not a production CORS policy. For any non-local deployment, backend CORS rules still need to be configured explicitly.
The Step 20 shell hardening pass keeps slash-command routing (`/pull`, `/brief`) centralized in the app layer, and the dev panel now keeps a rolling history of the latest five debug events for easier joint frontend-backend debugging.

First-pass frontend/backend integration artifacts live in:
- `docs/frontend-backend-integration-checklist.md`
- `docs/frontend-backend-integration-issues.md`

## Quick E2E Check

With the API running locally, you can exercise the current MVP backend in this order:

1. Ingest a user event:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/events/ingest -ContentType 'application/json' -Body '{"channel":"desktop_plugin","message_type":"text","text":"Just finished a heavy debugging session.","client_message_id":"manual-e2e-001","occurred_at":"2026-03-13T09:00:00+08:00"}'
```

2. Read the current state snapshot:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/state
```

3. Pull the next recommendation:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/recommendations/next
```

4. Read the brief summary:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/api/v1/brief
```

## Verify

```bash
pytest
```

Frontend verification:

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
```

If `pytest` fails with `PermissionError: [WinError 5]` on `E:\Antony\Documents`, run it through the local junction path instead:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\Antony\dev | Out-Null
if (-not (Test-Path C:\Users\Antony\dev\individual-assistant)) {
    New-Item -ItemType Junction -Path C:\Users\Antony\dev\individual-assistant -Target E:\Antony\Documents\individual-assistant | Out-Null
}
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m pytest C:\Users\Antony\dev\individual-assistant\tests -q
```
