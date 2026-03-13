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

### 1. Webhook duplicate suppression is only half complete
- Database uniqueness is implemented.
- Redis short-term duplicate suppression from the engineering addendum is not implemented yet.
- Impact: correctness is preserved, but webhook hot-loop efficiency is not fully aligned with the PM guidance.

### 2. Structured output path is still deterministic-only
- Current parser and profiling paths are conservative deterministic heuristics.
- The PM allows this ordering for MVP, but future LLM integration should be schema-first with validation and retry/fallback.

### 3. Push path only records decisions
- `mode='push'` recommendation records are created.
- External delivery and delivery-result handling are still absent.

### 4. Replay / rebuild exists in principle, not as a finished tool
- Fact and snapshot layers are separated correctly.
- There is no operator-facing replay command or rebuild script yet.

## Recommended next phase after MVP

1. Frontend integration against the stable API surface
2. Redis-backed webhook duplicate suppression
3. schema-first LLM structured output for parsing/profile/rendering
4. real push delivery channel and delivery audit outcomes

## Verification baseline

Latest local verification status:

- full test suite passes through the local junction path
- current count: `34 passed`
- application uses real PostgreSQL locally
- initial migration has been applied to the local `dln` database
