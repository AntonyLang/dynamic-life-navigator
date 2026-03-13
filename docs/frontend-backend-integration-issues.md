# Frontend/Backend Integration Issues

This file tracks the first integration-pass findings. Items are grouped by the categories agreed in the kickoff plan.

## frontend

### Open
- Explicit browser-side failure-copy forcing is still pending for:
  - recommendation `load_failed`
  - recommendation `feedback_failed`
  - Scope: validation follow-up only. Normal success flows and empty fallback were manually confirmed; only deliberate error-path display remains unforced in-browser.

### Resolved
- `vite dev` can be started successfully for live integration on this machine when launched from the approved command path.
  - Result: the React shell is reachable on `http://127.0.0.1:4173`, and the Vite proxy to `http://127.0.0.1:8000` is functioning.
  - Impact: live frontend/backend integration is no longer blocked by the earlier `EPERM` observation.
- Browser-side visual confirmation has now been completed for:
  - timeline progression to `synced`
  - dev panel refresh visibility after reset
  - brief panel rendering and refresh
  - accepted / snoozed / dismissed recommendation feedback flows

## backend

### Open
- none in the first live pass

### Resolved
- Local worker-off mode previously stalled after raw event ingest because `ENABLE_WORKER_DISPATCH=false` skipped parse/state/push entirely.
  - Fix: HTTP ingest routes now schedule an in-process FastAPI background pipeline when Celery dispatch is disabled.
  - Result: local chat/webhook flows can advance `event_logs -> state -> recommendation/push` without Redis/Celery.
- Real worker-on mode has now been verified with Redis + Celery enabled.
  - Result: `chat -> state -> recommendations -> feedback -> brief` behaves consistently with worker-off mode, while keeping request handling ack-only.
  - Impact: the async execution path is no longer only theoretically wired; it has been exercised end to end in the local environment.

## contract

### Open
- none in the first live pass

### Resolved
- none in the first live pass
- No contract drift was found between direct API usage and the Vite proxy path during the Step 22 smoke pass.
  - Result: the frontend can keep consuming the current stable response shapes without a compatibility shim.

## async-consistency

### Open
- none in the current proxy/API pass

### Resolved
- Real chat ingest now matches the frontend shell's short-poll reconcile assumption in local development.
  - Before the fix, the frontend could poll forever because the backend never advanced the event pipeline with workers disabled.
  - After the fix, the local background pipeline updates state and weak-push records asynchronously after the ack response.
- An immediate `GET /state` after `POST /chat/messages` can still return the pre-event snapshot, and that is expected under the current ack + background-task model.
  - Proxy-based live smoke against `http://127.0.0.1:4173/api/v1/...` confirmed convergence on the first poll in the frontend-style reconcile loop.
  - Result: frontend polling is required behavior here, not a contract drift.
- The same converge-after-ack behavior has now been confirmed in worker-on mode with a real Celery worker.
  - Result: the shell's reconcile loop does not need mode-specific logic for local background tasks versus Celery.

## ux-copy

### Open
- No product bug identified, but one deterministic-parser limitation remains visible in manual use:
  - Chinese freeform updates can fall through to `fallback` parse status and only update `recent_context`, while equivalent English keyword-driven messages currently produce energy/focus changes.
  - This is a known MVP parser limitation, not a worker-on integration regression.

### Resolved
- none in the first live pass
