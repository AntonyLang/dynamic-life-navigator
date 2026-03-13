# Dynamic Life Navigator

Backend foundation for the Dynamic Life Navigator MVP.

## Current scope

This repository currently provides:

- FastAPI application bootstrap
- environment-based settings
- request ID middleware and basic logging
- `/health` and `/ready` endpoints
- Celery bootstrap
- local Docker Compose for PostgreSQL and Redis

`ENABLE_WORKER_DISPATCH` defaults to `false` so request handlers stay fast even when Redis/workers are not running locally.
`DEFAULT_USER_ID` is the single-user MVP identity used by the current DB-backed services.

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

## Verify

```bash
pytest
```

If `pytest` fails with `PermissionError: [WinError 5]` on `E:\Antony\Documents`, run it through the local junction path instead:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\Antony\dev | Out-Null
if (-not (Test-Path C:\Users\Antony\dev\individual-assistant)) {
    New-Item -ItemType Junction -Path C:\Users\Antony\dev\individual-assistant -Target E:\Antony\Documents\individual-assistant | Out-Null
}
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m pytest C:\Users\Antony\dev\individual-assistant\tests -q
```
