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
- database-backed state updates, pull recommendations, feedback learning, and weak push delivery with attempt audit

`ENABLE_WORKER_DISPATCH` defaults to `false` so request handlers stay fast even when Redis/workers are not running locally.
`DEFAULT_USER_ID` is the single-user MVP identity used by the current DB-backed services.
The current push path supports a single outbound webhook sink. Delivery outcomes are summarized on `recommendation_records.delivery_status` and audited per attempt in `push_delivery_attempts`.

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

Step 22 integration verification was completed in both local async modes:
- `ENABLE_WORKER_DISPATCH=false`: FastAPI background pipeline advances `event_logs -> state -> weak push` after the ack
- `ENABLE_WORKER_DISPATCH=true`: Redis + Celery worker path advances the same loop and preserves the same frontend reconcile model

## Run a local push webhook sink

For real push delivery smoke tests, start the bundled webhook sink in a separate shell:

```powershell
python scripts/run_push_webhook_sink.py --host 127.0.0.1 --port 8787
```

Then configure push delivery in `.env` or your shell:

```text
PUSH_DELIVERY_ENABLED=true
PUSH_DELIVERY_CHANNEL=webhook_sink
PUSH_WEBHOOK_URL=http://127.0.0.1:8787/push
PUSH_WEBHOOK_TIMEOUT_SECONDS=10
PUSH_DELIVERY_MAX_ATTEMPTS=3
```

To simulate failures, restart the sink with a non-2xx status:

```powershell
python scripts/run_push_webhook_sink.py --host 127.0.0.1 --port 8787 --status-code 500
```

To inspect recent delivery attempts from the DB:

```powershell
python scripts/show_push_delivery_attempts.py --limit 10
```

For Windows local development, the verified worker-on combination is:
- API on `http://127.0.0.1:8000`
- Redis running through `docker compose up -d redis`
- Celery worker started with `-P solo`

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
Step 22 integration validation also re-checked the shell against the live Vite proxy on `http://127.0.0.1:4173/api/v1/...`.

First-pass frontend/backend integration artifacts live in:
- `docs/frontend-backend-integration-checklist.md`
- `docs/frontend-backend-integration-issues.md`

## Run the uTools plugin shell

The repository now also includes an independent uTools plugin project under `utools-plugin/`.
It reuses the existing backend contracts through a preload bridge, so the renderer does not call the backend directly and does not require backend CORS changes.

1. Keep the API running on `http://127.0.0.1:8000`.
2. Install plugin dependencies:

```powershell
cd C:\Users\Antony\dev\individual-assistant\utools-plugin
npm.cmd install
```

3. Start the plugin renderer dev server:

```powershell
cd C:\Users\Antony\dev\individual-assistant\utools-plugin
npm.cmd run dev
```

4. In the uTools developer tools, import the `utools-plugin` folder.
5. uTools will load:
   - `plugin.json`
   - `preload.js`
   - `development.main = http://127.0.0.1:5174/index.html`

The plugin exposes three feature codes:
- `shell`
- `pull`
- `brief`

Current plugin behavior:
- normal text goes to `POST /api/v1/chat/messages` with `channel=desktop_plugin`
- `/pull` calls `GET /api/v1/recommendations/next`
- `/brief` calls `GET /api/v1/brief`
- recommendation feedback uses the existing `POST /api/v1/recommendations/{id}/feedback`
- image launch payloads are acknowledged locally as "已收到图片，暂未解析。"

For an offline/importable build:

```powershell
cd C:\Users\Antony\dev\individual-assistant\utools-plugin
npm.cmd run build
```

Keep these files together when importing the built plugin folder into uTools:
- `plugin.json`
- `preload.js`
- `logo.svg`
- `dist/`

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

## Quick push delivery smoke

1. Start the local webhook sink:

```powershell
python scripts/run_push_webhook_sink.py --host 127.0.0.1 --port 8787
```

2. Configure `PUSH_WEBHOOK_URL=http://127.0.0.1:8787/push`.
3. Start the API in either:
   - `ENABLE_WORKER_DISPATCH=false`
   - `ENABLE_WORKER_DISPATCH=true` with Redis + Celery
4. Trigger an event or state change that generates a push recommendation.
5. Verify:
   - the sink prints one webhook payload
   - `recommendation_records.mode='push'`
   - `recommendation_records.delivery_status='sent'`
   - `scripts/show_push_delivery_attempts.py` shows a `sent` attempt

For a failure smoke:

1. Restart the sink with `--status-code 500`
2. Trigger another push recommendation
3. Verify:
   - delivery ends as `failed`
   - three attempt rows are recorded

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

uTools plugin verification:

```powershell
cd C:\Users\Antony\dev\individual-assistant\utools-plugin
npm.cmd run test
npm.cmd run build
```

Integration verification status after Step 22:
- backend full suite: `44 passed`
- frontend test suite: `20 passed`
- frontend build: passed
- direct API smoke: passed on `127.0.0.1:8000`
- Vite proxy smoke: passed on `127.0.0.1:4173`
- worker-on Celery path: passed with Redis + `celery ... -P solo`

If `pytest` fails with `PermissionError: [WinError 5]` on `E:\Antony\Documents`, run it through the local junction path instead:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\Antony\dev | Out-Null
if (-not (Test-Path C:\Users\Antony\dev\individual-assistant)) {
    New-Item -ItemType Junction -Path C:\Users\Antony\dev\individual-assistant -Target E:\Antony\Documents\individual-assistant | Out-Null
}
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m pytest C:\Users\Antony\dev\individual-assistant\tests -q
```

The same Windows path workaround applies to the uTools plugin Node commands on this machine.
Prefer running `npm.cmd run test` and `npm.cmd run build` from:

```powershell
C:\Users\Antony\dev\individual-assistant\utools-plugin
```
