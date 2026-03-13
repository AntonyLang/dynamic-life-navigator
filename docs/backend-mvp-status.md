# Backend MVP Status

This document tracks the current backend MVP boundary against the PM documents and `AGENTS.md`.

## Current assessment

The backend is now functionally at the MVP-complete threshold for the deterministic single-user scope.

That means the core loop is present and test-covered:

1. ingest raw events
2. persist facts in `event_logs`
3. parse into conservative structured impact
4. update snapshot state in `user_state`
5. generate pull recommendations
6. persist recommendation records and feedback
7. evaluate weak push opportunities

## Implemented MVP capabilities

### Runtime and ops
- FastAPI app factory with `/health` and `/ready`
- environment-based settings
- request ID propagation
- structured logging helpers
- local PostgreSQL / Redis / Celery bootstrap
- Redis-backed webhook duplicate suppression with DB uniqueness as the final correctness layer
- Alembic migration path

### Core data model
- `user_state`
- `state_history`
- `action_nodes`
- `node_annotations`
- `event_logs`
- `recommendation_records`
- `recommendation_feedback`

### API surface
- `POST /api/v1/chat/messages`
- `POST /api/v1/events/ingest`
- `POST /api/v1/webhooks/{source}`
- `GET /api/v1/state`
- `POST /api/v1/state/reset`
- `GET /api/v1/recommendations/pull`
- `GET /api/v1/recommendations/next`
- `GET /api/v1/recommendations/brief`
- `GET /api/v1/brief`
- `POST /api/v1/recommendations/{recommendation_id}/feedback`
- `POST /api/v1/nodes`

### Recommendation loop
- candidate filtering
- deterministic ranking
- documented `+10` energy tolerance buffer for recommendation matching
- cooldown / suppression
- rejection penalty
- recent completion penalty
- exposure fatigue penalty
- no-candidate fallback
- recommendation audit persistence
- node-level feedback projection

### Async/background loop
- parse event logs
- apply state patches with optimistic concurrency
- evaluate weak push opportunities
- enrich active nodes
- compress old event logs
- recalculate dynamic urgency scores
- backfill async node profiles

## MVP gaps intentionally left out

These are real product capabilities, but they are not required to call the current backend MVP-ready:

- real external push delivery
- LLM-backed structured parser / renderer
- remote enrichment sources
- advanced replay tooling over `event_logs`
- multi-user / multi-tenant isolation
- rich frontend integration
- production telemetry stack such as Prometheus / Sentry / OpenTelemetry

## Known non-MVP gaps still worth tracking

These are the next likely engineering moves after MVP:

### 1. Structured output path is still deterministic-only
- Current parser and profiling paths are conservative deterministic heuristics.
- The PM allows this ordering for MVP, but future LLM integration should be schema-first with validation and retry/fallback.

### 2. Push path only records decisions
- `mode='push'` recommendation records are created.
- External delivery and delivery-result handling are still absent.

### 3. Replay / rebuild exists in principle, not as a finished tool
- Fact and snapshot layers are separated correctly.
- There is no operator-facing replay command or rebuild script yet.

## Recommended next phase after MVP

Frontend integration against the stable API surface has now been completed for the MVP shell.

The next priorities are:

1. schema-first LLM structured output for parsing/profile/rendering
2. multilingual / broader deterministic parser coverage where MVP heuristics are currently too narrow
3. real push delivery channel and delivery audit outcomes
4. replay / rebuild tooling over `event_logs`

## Verification baseline

Latest local verification status:

- full test suite passes through the local junction path
- current backend count: `44 passed`
- frontend integration has been validated through:
  - frontend tests
  - direct API/proxy smoke
  - manual browser walkthrough
- application uses real PostgreSQL locally
- initial migration has been applied to the local `dln` database
