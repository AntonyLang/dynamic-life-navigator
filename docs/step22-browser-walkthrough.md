# Step 22 Browser Walkthrough

## Goal

Do a real browser-side manual integration walkthrough for the MVP shell.

This is a validation pass, not a feature task.
Do not change code unless you hit:
- a clear frontend-consumption bug, or
- a backend behavior that violates the current contract.

If you find a problem, report it first with evidence.

## Context

- Backend MVP is already API-verified.
- Frontend shell is already test/build verified.
- Remaining gap is browser-visible confirmation:
  - timeline status reaches `synced`
  - dev panel refresh visibility after reset/create node
  - recommendation load failure vs feedback failure copy
- Async model is intentional:
  - request returns ack first
  - state may update shortly after
  - frontend uses short polling to reconcile

Please run this in 2 phases.

## Phase 1: worker-off browser walkthrough

### Environment

- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:4173`
- `ENABLE_WORKER_DISPATCH=false`

### Start commands

#### 1. Redis

```powershell
cd /d E:\Antony\Documents\individual-assistant
docker compose up -d redis
```

#### 2. Backend

```powershell
cd /d E:\Antony\Documents\individual-assistant
$env:ENABLE_WORKER_DISPATCH='false'
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

#### 3. Frontend

```powershell
cd /d C:\Users\Antony\dev\individual-assistant\frontend
npm.cmd run dev -- --host 127.0.0.1 --port 4173
```

### Browser target

`http://127.0.0.1:4173`

### Walkthrough steps

#### 1. Initial load

- Confirm the page loads.
- Confirm the state bar renders.
- If state fetch fails, confirm the shell does not hard-block.

#### 2. Reset baseline in dev panel

Use:
- `mental_energy = 100`
- `physical_energy = 100`
- `reason = manual qa baseline`

Expected:
- state bar updates
- debug section shows a new `request_id`

#### 3. Create two nodes in dev panel

Node A:
- `drive_type = project`
- `title = Take a small recovery walk`
- `summary = Light recovery after a heavy focus block`
- `tags = recovery,light,outdoor`
- `priority_score = 80`
- `dynamic_urgency_score = 70`
- `estimated_minutes = 10`

Node B:
- `drive_type = project`
- `title = Organize inbox for 10 minutes`
- `summary = Low-pressure cleanup task`
- `tags = admin,indoor,light`
- `priority_score = 65`
- `dynamic_urgency_score = 55`
- `estimated_minutes = 10`

Expected:
- create succeeds
- debug section updates
- later `/pull` or `/brief` reflects the new nodes

#### 4. Chat flow

Input:

`刚刚连续 debug 了两小时，现在脑子很累。`

Expected:
- optimistic user bubble appears immediately
- assistant ack appears
- message status eventually reaches `synced`
- within a few seconds, state bar reflects a more tired state
- `request_id` and preferably `event_id` are visible in debug info

#### 5. Pull flow

Use `/pull` or the pull button.

Expected:
- recommendation card appears, or fallback block appears if empty
- if loading fails, UI shows a load failure state, not a feedback failure state
- `recommendation_id` is visible in debug info if possible

#### 6. Feedback flow

Test:
- `accepted`
- then `/pull` again
- `dismissed` / `换一个`
- then `/pull` again
- `snoozed` / `稍后`

Expected:
- buttons disable while feedback is submitting
- status resolves cleanly after submit
- `dismissed` triggers repull behavior
- feedback errors, if any, are distinct from recommendation load errors

#### 7. Brief flow

Use `/brief` or the brief button.

Expected:
- brief panel opens
- summary and items render
- panel can refresh while open

#### 8. Dev panel linkage

Do another reset:
- `mental_energy = 30`
- `physical_energy = 70`
- `reason = manual low energy check`

Then run `/pull` again.

Expected:
- state bar updates
- recommendation/brief visibly reflect the new state
- debug history keeps the latest 5 events, not only 1

## Phase 2: worker-on spot check

### Environment

- `ENABLE_WORKER_DISPATCH=true`
- Redis running
- Celery worker running

### Start worker

```powershell
cd /d E:\Antony\Documents\individual-assistant
$env:ENABLE_WORKER_DISPATCH='true'
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m celery -A app.workers.celery_app:celery_app worker -l info -P solo
```

### Restart backend with worker-on

```powershell
cd /d E:\Antony\Documents\individual-assistant
$env:ENABLE_WORKER_DISPATCH='true'
& 'C:\Users\Antony\AppData\Local\Programs\Python\Python312\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Repeat this minimal chain in the browser

1. reset baseline
2. send one chat:
   - `刚做完很重的脑力活，想先缓一下。`
3. run `/pull`
4. click `accepted`
5. open `/brief`

Expected:
- ack-first behavior still holds
- state still converges inside the existing reconcile window
- recommendation / feedback / brief behavior matches worker-off mode closely

## What to report back

For every issue, report using this template:

- Mode:
- Action:
- Expected:
- Actual:
- `request_id`:
- `event_id` or `recommendation_id`:
- Screenshot:
- Console/network notes:

If there is no issue, return a compact summary with:
- worker-off result
- worker-on result
- whether `synced` was visually confirmed
- whether dev panel refresh was visually confirmed
- whether `load_failed` vs `feedback_failed` copy was visually confirmed

## Important constraints

- Do not redesign UI
- Do not add features
- Do not change API shapes
- Only patch code if you find a clear implementation bug, and if you do, explain the bug and the fix
