# Frontend/Backend Integration Checklist

This checklist tracks the first real integration pass between the React shell and the FastAPI MVP backend.

## Current baseline

- Backend automated verification: `44 passed`
- Frontend automated verification: `20 passed`
- Frontend production build: passed
- Full backend suite re-run from a clean baseline and confirmed to leave `user_state` clean
- Real API smoke pass completed against a live local uvicorn instance on `127.0.0.1:8000`
- Real proxy smoke pass completed against the Vite shell proxy on `http://127.0.0.1:4173/api/v1/...`
- Real worker-on smoke pass completed with:
  - `ENABLE_WORKER_DISPATCH=true`
  - Redis from `docker compose`
  - Celery worker using `-P solo`
- Local smoke confirmed:
  - `POST /api/v1/chat/messages`
  - `GET /api/v1/state`
  - `POST /api/v1/state/reset`
  - `POST /api/v1/nodes`
  - `GET /api/v1/recommendations/next`
  - `POST /api/v1/recommendations/{id}/feedback`
  - `GET /api/v1/brief`

## Phase A: runtime baseline and observability

### API runtime
- Steps:
  - start `uvicorn app.main:app --host 127.0.0.1 --port 8000`
  - call `GET /health`
  - call `GET /api/v1/state`
- Expected UI:
  - state bar can render a valid snapshot
  - no frontend blocking on initial state fetch
- Expected API:
  - `/health` returns `{"status":"ok"}`
  - `/api/v1/state` returns `request_id + state`
- Expected DB:
  - `user_state` row exists for `DEFAULT_USER_ID`
- First-pass status:
  - passed in live API smoke

### Debug visibility
- Steps:
  - submit one chat message
  - pull one recommendation
  - submit one feedback action
- Expected UI:
  - dev panel shows `request_id`
  - chat ack shows `event_id`
  - latest recommendation/debug entry exposes `recommendation_id`
- Expected API:
  - all responses return `X-Request-Id`
- Expected DB:
  - `event_logs`, `recommendation_records`, `recommendation_feedback` are queryable by those IDs
- First-pass status:
  - API side passed
  - browser-side visual confirmation later passed in manual walkthrough:
    - debug panel showed `request_id`
    - chat ACK exposed `event_id`
    - recommendation feedback exposed `recommendation_id`

## Phase B: five golden flows

### 1. Chat record flow
- Steps:
  - send plain text through `POST /api/v1/chat/messages`
  - fetch `GET /api/v1/state`
- Expected UI:
  - optimistic user bubble
  - assistant ack bubble
  - timeline status progresses to `synced`
  - state bar eventually reflects the new focus mode/context
- Expected API:
  - chat returns `accepted=true`, `processing=true`, `event_id`
  - state request reflects the parsed state update
- Expected DB:
  - `event_logs` row inserted
  - `state_history` row inserted for the event
  - optional weak-push `recommendation_records` row may be generated
- First-pass status:
  - passed in live API smoke after local background pipeline fallback was added
  - passed again through the frontend proxy path on `http://127.0.0.1:4173/api/v1/...` when using the shell's short-poll reconcile model
  - passed again in worker-on mode with Redis + Celery; the second state poll converged to the post-chat snapshot under the same reconcile window
  - browser-side walkthrough also visually confirmed the timeline reaching `synced` in both worker-off and worker-on checks

### 2. Pull recommendation flow
- Steps:
  - trigger `/pull` or call `GET /api/v1/recommendations/next?limit=1`
- Expected UI:
  - recommendation card renders when candidates exist
  - fallback block renders when `empty_state=true`
  - load failures render `load_failed`, not feedback errors
- Expected API:
  - returns `recommendation_id`, `empty_state`, `items`, `fallback_message`
- Expected DB:
  - `recommendation_records.mode='pull'`
  - `selected_node_ids` matches rendered items when non-empty
- First-pass status:
  - passed in live API smoke with a temporary node created through `POST /api/v1/nodes`
  - passed again through the frontend proxy path
  - passed again in worker-on mode after the chat-driven state update converged

### 3. Brief flow
- Steps:
  - trigger `/brief` or call `GET /api/v1/brief`
- Expected UI:
  - brief panel opens and renders summary/items
  - refresh action works while panel is open
- Expected API:
  - returns `summary + items`
- Expected DB:
  - reflects currently active nodes and their urgency/staleness
- First-pass status:
  - passed in live API smoke
  - passed again through the frontend proxy path
  - passed again in worker-on mode

### 4. Recommendation feedback flow
- Steps:
  - submit `accepted`, `snoozed`, or `dismissed`
  - if `dismissed`, verify repull path
- Expected UI:
  - buttons disable during `feedback_submitting`
  - status returns to `feedback_done` or `feedback_failed`
  - `dismissed` triggers a repull
- Expected API:
  - `POST /api/v1/recommendations/{id}/feedback` returns `accepted=true`
- Expected DB:
  - `recommendation_feedback` row inserted
  - node signals update according to feedback type
- First-pass status:
  - `accepted` path passed in live API smoke
  - `accepted` path also passed through the frontend proxy path
  - `accepted` path also passed in worker-on mode
  - browser-side walkthrough confirmed:
    - `accepted`
    - `snoozed`
    - `dismissed -> repull`
  - with the current tiny two-node manual test pool, repull can legitimately land on empty fallback after cooldown/exposure rules apply

### 5. Dev panel state/node flow
- Steps:
  - submit `POST /api/v1/state/reset`
  - submit `POST /api/v1/nodes`
  - repull recommendation and brief
- Expected UI:
  - state bar updates after reset
  - recommendation/brief changes become visible
  - debug history keeps latest five events
- Expected API:
  - reset returns updated state
  - node create returns accepted node payload
- Expected DB:
  - `state_history` row for reset
  - `action_nodes` row for created node
- First-pass status:
  - API side passed in live smoke
  - proxy/API side also passed against the live Vite shell proxy
  - data-side behavior also passed in worker-on mode via reset -> create node -> repull/brief API checks
  - browser-side walkthrough confirmed:
    - reset visibly updated the state bar
    - create-node effects were visible in recommendation/brief flows
    - debug history retained the latest five events

## Phase C: async consistency checks

### Worker-off local integration mode
- Steps:
  - keep `ENABLE_WORKER_DISPATCH=false`
  - submit chat or webhook input through HTTP routes
- Expected UI:
  - frontend reconcile can observe the eventual state update
- Expected API:
  - request path stays ack-style
  - no Redis/Celery requirement for local MVP loop progression
- Expected DB:
  - background parse/state/push side effects still occur
- First-pass status:
  - passed after adding a FastAPI `BackgroundTasks` fallback
  - clarified in live proxy smoke: an immediate post-chat `GET /state` may still show the pre-event snapshot, but the first short poll converged correctly

### Worker-on Celery integration mode
- Steps:
  - set `ENABLE_WORKER_DISPATCH=true`
  - run Redis locally
  - start a real Celery worker
  - submit chat input, then poll `GET /api/v1/state`
- Expected UI:
  - frontend reconcile window still converges without changing shell behavior
- Expected API:
  - request path stays ack-style
  - Celery path replaces the local FastAPI background pipeline as the main async executor
- Expected DB:
  - event parse/state/recommendation side effects appear through worker execution
- First-pass status:
  - passed in direct API smoke and again through the Vite proxy path
  - no behavior drift observed versus worker-off mode

### Stale/error semantics
- Steps:
  - simulate state fetch failure or stale snapshot age
  - simulate recommendation pull failure
- Expected UI:
  - state bar shows stale status clearly
  - recommendation timeline uses `load_failed`
  - feedback errors stay separate from load errors
- Expected API:
  - no contract change
- Expected DB:
  - no extra side effects required
- First-pass status:
  - covered by automated frontend tests
  - browser-side walkthrough confirmed normal success states and empty fallback behavior
  - explicit failure-copy forcing (`load_failed` vs `feedback_failed`) remains covered by automated frontend tests rather than a manually induced browser error
