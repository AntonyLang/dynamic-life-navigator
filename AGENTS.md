# AGENTS.md

## Project identity
This repository implements a personal navigation assistant / value-driven personal operating system.
It is not a generic todo app.
The product goal is to turn user inputs, state changes, and external events into context-aware next-action recommendations.

Core architecture:
- Service + Worker + Data Loop
- fact layer (`event_logs`) separated from snapshot layer (`user_state`)
- recommendation pipeline = Filter + Ranker + Renderer
- MVP-first, commercializable, engineering-rigorous

## Source of truth
Before making major implementation decisions, read these documents in this order:

1. `revised_pm/07_Engineering_Addendum_V2_1.md`
2. `revised_pm/02_API_Workflows_Prompts_V2.md`
3. `revised_pm/03_Database_Schema_V2.md`
4. `revised_pm/05_System_Architecture_V2.md`
5. `revised_pm/01_PRD_V2.md`
6. `revised_pm/04_Frontend_Design_V2.md`
7. `revised_pm/06_User_Scenarios_Validation_V2.md`
8. `revised_pm/00_Revision_Summary.md`

If documents conflict, follow the order above.

## Working style
- Prefer conservative, high-confidence changes.
- Do not over-design.
- Do not silently invent new product directions.
- Keep the implementation aligned with the PM documents.
- Make the smallest change that preserves long-term extensibility.
- Explain implementation tradeoffs when they matter.
- After each major step, report:
  - files changed
  - what was implemented
  - what remains
  - how to run or verify

## MVP boundaries
For the current phase:
- Single-user-first is acceptable.
- One primary input channel is enough.
- Pull flows and weak push are enough.
- Deterministic recommendation logic comes before deep LLM integration.
- Do not build multi-tenant architecture unless explicitly requested.
- Do not build unnecessary multimodal ingestion yet.

## Required stack defaults
Unless the repository already has an established alternative, prefer:
- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- Alembic
- PostgreSQL
- Redis
- Celery
- pytest
- httpx
- docker compose

## Required backend structure
Prefer a structure close to:

- `app/api/`
- `app/core/`
- `app/db/`
- `app/models/`
- `app/schemas/`
- `app/services/`
- `app/workers/`
- `app/ranking/`
- `app/prompts/`
- `app/telemetry/`
- `tests/`
- `migrations/`

Do not create giant files or god services.
Keep domain models, transport schemas, and service logic reasonably separated.

## Engineering constraints that must be preserved

### 1) Event ingest must stay low-latency
Synchronous ingest should only:
- receive input
- validate it
- persist raw event / event log
- perform idempotency checks
- return ack

Heavy parsing, enrichment, state recomputation, and recommendation refresh must run asynchronously.

### 2) New action nodes must not block on LLM profiling
If a new node is created without energy profile fields:
- set `mental_energy_required = 50`
- set `physical_energy_required = 20`
- set low confidence defaults
- enqueue async profiling for later backfill

Node creation must succeed even if profiling fails.

### 3) Structured outputs must be schema-first
Any future LLM structured output flow must be designed around:
- schema-bound output when possible
- JSON mode or equivalent structured decoding
- runtime validation
- retry + fallback strategy

Do not rely only on prompt text asking the model to “return JSON”.

### 4) Idempotency must be two-layered
Use:
- Redis short-term idempotency / duplicate suppression
- database uniqueness as the final correctness guard and audit layer

Do not rely on only one of them.

### 5) State model rules
- `event_logs` is the fact layer
- `user_state` is a snapshot layer
- snapshots should be rebuildable from facts in principle
- use optimistic concurrency with `state_version`
- design state updates so replay/rebuild remains possible later

### 6) Recommendation loop rules
Recommendation logic must include:
- candidate filtering
- ranking
- cooldown / suppression
- recent rejection penalty
- no-candidate fallback behavior

Feedback must be persisted through:
- `recommendation_records`
- `recommendation_feedback`

Do not skip the feedback loop.

## Database expectations
At minimum, preserve and implement these core entities:
- `user_state`
- `action_nodes`
- `node_annotations`
- `event_logs`
- `recommendation_records`
- `recommendation_feedback`

When in doubt:
- keep stable query fields relational
- keep flexible enrichment payloads in JSON/JSONB
- add indexes for operationally important queries
- make idempotency and state concurrency explicit in schema design

## API expectations
At minimum, preserve these endpoint contracts or their clear equivalents:
- `POST /events/ingest`
- `GET /state`
- `GET /recommendations/next`
- `POST /recommendations/{id}/feedback`
- `GET /brief`

All externally exposed endpoints should have:
- request schema
- response schema
- explicit error handling
- stable naming

## Testing expectations
Every meaningful implementation step should add or update tests.

At minimum keep:
- config / settings tests
- health check test
- one API flow test
- one recommendation/ranking rule test
- migration sanity

Avoid merging large changes without verification steps.

## Operational expectations
Always include:
- environment-based config
- logging
- local dev startup instructions
- migration path
- basic health check
- error handling

Do not leave the repo in a state where code exists but cannot be run locally.

## Documentation expectations
If implementation changes assumptions, update the relevant docs.
If a recurring correction is made, update this `AGENTS.md` too so the correction persists.

## What to avoid
- Do not turn this into a generic task manager.
- Do not put LLM calls directly on critical synchronous paths unless explicitly justified.
- Do not skip migrations.
- Do not skip tests.
- Do not introduce hidden coupling between API schemas and internal storage models.
- Do not overfit the codebase to one temporary demo path.

## Default execution pattern
When asked to implement substantial work:
1. Inspect repository and relevant docs first.
2. Produce a concise implementation plan.
3. Execute in small, reviewable steps.
4. Run tests / verification commands.
5. Report changes and remaining risks.