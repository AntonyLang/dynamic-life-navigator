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

Parser quality has also moved beyond the original English-only MVP heuristic:

- deterministic rule-driven parsing now covers the first Chinese/English multilingual signal set
- fallback behavior still exists, but equivalent mental-load / recovery / movement expressions no longer depend on English-only keywords
- node profiling now shares the same signal vocabulary baseline as event parsing
- schema-first parser integration now exists behind provider boundaries, with deterministic parsing kept as the authoritative baseline
- Gemini has been validated in both `worker-off` and `worker-on` live paths, but it is currently used in shadow mode rather than as the primary state-writing parser
- async node profiling now mirrors the same shadow-first pattern:
  - deterministic remains authoritative
  - Gemini can run as a non-authoritative shadow profile provider
  - profile comparison data is stored in `action_nodes.ai_context`

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
- `push_delivery_attempts`

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
- deliver weak push recommendations through a single webhook sink
- enrich active nodes
- compress old event logs
- recalculate dynamic urgency scores
- backfill async node profiles

## MVP gaps intentionally left out

These are real product capabilities, but they are not required to call the current backend MVP-ready:

- LLM-backed structured parser / renderer
- remote enrichment sources
- advanced replay tooling over `event_logs`
- multi-user / multi-tenant isolation
- rich frontend integration
- production telemetry stack such as Prometheus / Sentry / OpenTelemetry

## Known non-MVP gaps still worth tracking

These are the next likely engineering moves after MVP:

### 1. Structured output path is shadow-first, not primary
- Schema-first parser providers now exist for:
  - deterministic
  - `structured_stub`
  - `structured_model_shell`
  - `openai_responses`
  - `gemini_direct`
- The current PM-aligned operating mode is:
  - deterministic remains authoritative
  - Gemini runs as a non-blocking shadow parser
  - state updates still come only from the authoritative deterministic parse
- `event_logs.parse_metadata` now records:
  - primary parser metadata
  - shadow parser metadata
  - comparison result (`exact_match`, `compatible_match`, `drift`, `shadow_failed`)
- This gives the project a schema-first comparison loop without risking state drift in the main recommendation cycle.

### 2. Push delivery is now single-channel and audit-backed
- `mode='push'` recommendation records can now move through:
  - `generated`
  - `sent`
  - `failed`
  - `skipped`
- Real outbound delivery now exists for a single channel:
  - `webhook_sink`
- Delivery attempts are audited in `push_delivery_attempts`, including:
  - request payload
  - response status
  - response/error detail
  - per-attempt timestamps
- This is intentionally still v1:
  - no HMAC signing
  - no per-user push settings
  - no open/disable feedback loop yet

### 3. Replay / rebuild exists in principle, not as a finished tool
- Fact and snapshot layers are separated correctly.
- There is no operator-facing replay command or rebuild script yet.

## Recommended next phase after MVP

Frontend integration against the stable API surface has now been completed for the MVP shell.

The deterministic multilingual parser expansion has also been completed as the first post-MVP quality pass.

The next priorities are:

1. real push delivery channel and delivery audit outcomes
2. replay / rebuild tooling over `event_logs`
3. broader deterministic and canonical Gemini coverage where shadow data still shows drift
4. operator-facing review surfaces for parser/profile shadow comparison data

## Verification baseline

Latest local verification status:

- full test suite passes through the local junction path
- current backend count: `120 passed`
- frontend integration has been validated through:
  - frontend tests
  - direct API/proxy smoke
  - manual browser walkthrough
- Gemini live parser validation has now been completed through:
  - `worker-off` with a real AI Studio key
  - `worker-on` with Redis + Celery
  - both modes showing `parser_provider=gemini_direct` without transport fallback
- profiling parity verification now includes:
  - deterministic authoritative profile writes
  - Gemini shadow profile comparison writes
  - exact / compatible / drift / shadow_failed comparison result coverage
- real push delivery verification now includes:
  - webhook sink delivery service
  - per-attempt audit rows in `push_delivery_attempts`
  - worker-off and worker-on delivery wiring tests
- application uses real PostgreSQL locally
- initial migration has been applied to the local `dln` database
