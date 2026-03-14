# Post-Integration Closeout

This document closes out the first MVP frontend/backend integration phase.

## Final assessment

The current repository is now past the "backend MVP complete" threshold and has also completed the first meaningful frontend/backend integration pass.

For the current deterministic single-user MVP scope, the product loop is now validated at three levels:

1. automated backend verification
2. automated frontend verification
3. live local integration in both async modes

That means the project is no longer in a "backend ready, frontend still theoretical" state. The shell, API surface, database, and async execution model have now been exercised together.

## What is now confirmed

### Backend baseline
- FastAPI + PostgreSQL + Redis + Celery stack is in place
- core fact/snapshot/recommendation tables are live
- full backend suite passes locally
- latest baseline: `143 passed`

### Frontend baseline
- React + Vite thin client is in place
- command-driven MVP shell is working
- frontend tests and production build pass locally
- latest baseline:
  - `20` frontend tests passed
  - production build passed

### Integration baseline
The following are now confirmed in live use:

- `worker-off` mode
  - FastAPI background pipeline
  - chat -> state -> recommendation -> feedback -> brief loop works
- `worker-on` mode
  - Redis + Celery worker path
  - the same loop works without contract drift
- browser-side visual confirmation
  - timeline reaches `synced`
  - dev panel reset visibly updates state
  - recommendation feedback flows work
  - brief panel opens and refreshes
  - debug history retains recent events

## Proven MVP behavior

The current MVP can now be described as:

- user submits an update or direct request
- backend records the event
- state converges asynchronously
- recommendation pull works with deterministic ranking
- feedback persists and affects node signals
- brief summarizes the current active surface
- weak push decisions can now be delivered through a single webhook sink with attempt audit

This has now been verified:
- by automated tests
- by direct API/proxy smoke
- by manual browser walkthrough

## What is still not fully closed

These are not MVP blockers, but they are real remaining gaps:

### 1. Browser failure-copy forcing
We did not deliberately force browser-visible error states for:
- recommendation `load_failed`
- recommendation `feedback_failed`

Those states are covered by frontend automated tests, but not yet manually forced in-browser.

### 2. Push delivery is still intentionally narrow
Weak push is no longer decision-only:
- a single webhook sink channel now exists
- delivery attempts are audited

But v1 still omits:
- per-user push preferences
- multi-channel delivery
- push open / disable event feedback

### 3. Gemini is connected, but still shadow-first by design
- The Gemini provider path is now live-validated in:
  - `worker-off`
  - `worker-on`
- That means schema-first Gemini parsing is no longer merely theoretical.
- However, Gemini is intentionally not the authoritative parser yet.
- The current PM-aligned operating mode is:
  - deterministic is the primary parser and state-writing authority
  - Gemini runs as a non-authoritative shadow parser for comparison and observability
- This keeps the state/recommendation loop conservative while real shadow data is collected.

### 4. Replay/rebuild and shadow review are now operator-usable
- replay/rebuild remains dry-run only, but bounded-window correctness has now been hardened
- parser/profile shadow comparison data now has dedicated operator CLI review surfaces
- this means the current post-MVP work can be driven by actual drift reports rather than ad hoc log inspection

## Recommended next phase

Now that MVP integration is closed enough to move on, the next priorities should be:

1. broader canonicalization and drift reduction
   - use the new replay/rebuild hardening and shadow review surfaces as the evidence base
   - keep extending deterministic fallback where real usage still falls through
   - tighten Gemini prompt/schema based on parser and profile shadow comparison results

2. guarded replay/rebuild evolution
   - keep dry-run tooling authoritative and trustworthy
   - do not add `rebuild --apply` until drift data stays stable

3. selective frontend refinement
   - only after parser/push priorities are clearer
   - keep the shell thin unless a real product surface is chosen

## Recommendation on project state

For the current phase, this project can reasonably be treated as:

- backend MVP complete
- frontend integration MVP complete
- ready to transition into post-MVP hardening / product-depth work

## Verification references

Primary documents for the current state:

- `docs/backend-mvp-status.md`
- `docs/frontend-backend-integration-checklist.md`
- `docs/frontend-backend-integration-issues.md`
- `docs/development-logs/2026-03-13.md`
- `docs/development-logs/2026-03-14.md`
