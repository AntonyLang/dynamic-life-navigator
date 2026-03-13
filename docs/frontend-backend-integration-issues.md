# Frontend/Backend Integration Issues

This file tracks the first integration-pass findings. Items are grouped by the categories agreed in the kickoff plan.

## frontend

### Open
- Browser-side manual confirmation is still pending for:
  - timeline status progression to `synced`
  - dev panel refresh visibility after reset/create node
  - recommendation load vs feedback error copy in a real page session
  - Scope: integration follow-up work, not an identified contract or backend bug.

### Resolved
- `vite dev` can be started successfully for live integration on this machine when launched from the approved command path.
  - Result: the React shell is reachable on `http://127.0.0.1:4173`, and the Vite proxy to `http://127.0.0.1:8000` is functioning.
  - Impact: live frontend/backend integration is no longer blocked by the earlier `EPERM` observation.

## backend

### Open
- none in the first live pass

### Resolved
- Local worker-off mode previously stalled after raw event ingest because `ENABLE_WORKER_DISPATCH=false` skipped parse/state/push entirely.
  - Fix: HTTP ingest routes now schedule an in-process FastAPI background pipeline when Celery dispatch is disabled.
  - Result: local chat/webhook flows can advance `event_logs -> state -> recommendation/push` without Redis/Celery.

## contract

### Open
- none in the first live pass

### Resolved
- none in the first live pass

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

## ux-copy

### Open
- none identified in the first live pass

### Resolved
- none in the first live pass
