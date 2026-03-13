# Parser Quality Expansion Review

This document archives the review conclusion for the deterministic multilingual parser-quality pass completed after the first MVP integration closeout.

## Summary

The parser and node-profiling changes are accepted.

They align with the PM and engineering addendum as a quality-expansion step on top of the existing MVP loop, not as a product-direction change. The work preserves the existing fact/snapshot architecture, keeps the API surface stable, and improves consistency between English and Chinese input handling.

## PM and Architecture Alignment

### Event facts and snapshot state
- `event_logs` remains the fact layer.
- `user_state` remains the snapshot layer.
- `parse_event_log()` still records parse results and `parse_status` on the event row.
- `apply_state_patch_from_event()` still updates `user_state` through optimistic concurrency and writes `state_history`.

This matches the constraints in the database schema and engineering addendum documents.

### Low-latency ingest and async processing
- HTTP ingest remains ack-first.
- Heavy parse/state/recommendation work still runs asynchronously:
  - FastAPI background pipeline in worker-off mode
  - Celery worker path in worker-on mode

This preserves the intended service + worker split.

### Node cold-start profiling
- New nodes still start with conservative defaults.
- Deterministic heuristics only prefill a safe profile.
- Async profiling still backfills richer values later.

This remains consistent with the cold-start strategy defined in the engineering addendum.

## Implementation Assessment

### Shared signal catalog
- `app/services/signal_catalog.py` centralizes multilingual signal definitions and parser priority.
- Parser and node profiling now share the same vocabulary baseline.
- The current signal groups are:
  - `mental_load`
  - `recovery`
  - `movement`
  - `light_admin`
  - `coordination`
  - `deep_focus`

This is the right direction: it removes scattered conditional logic and makes future signal expansion easier to review.

### Event parsing
- `app/services/event_processing.py` now maps text -> signal -> structured parser output.
- `ParsedImpact` and `ParseResult` remain stable.
- Internal `event_type` values were extended to include `light_admin` and `coordination` without changing external contracts.
- Fallback behavior is now safer:
  - unmatched events still update `recent_context`
  - fallback no longer resets `focus_mode` to `unknown`

That fallback correction closes a real state-quality bug and matches the intended conservative-degradation rule.

### Node profiling
- `app/services/node_profile_service.py` now uses the same signal catalog semantics.
- Profiling remains deterministic and async.
- `ai_context.profile_method` is explicitly versioned as `deterministic_async_v2`.

This is a good intermediate milestone before any schema-first LLM-backed profiling work.

## Test and Integration Assessment

### Backend tests
The expanded tests now cover:
- Chinese and English `mental_load`
- Chinese `recovery`
- Chinese `movement`
- `light_admin`
- `coordination`
- parser priority behavior
- fallback preserving state while updating context
- worker-off route-level Chinese convergence
- worker-on dispatch-path Chinese convergence
- Chinese node profiling cases

### Integration stability
- No API shape changed.
- Frontend integration continued to work across:
  - worker-off mode
  - worker-on mode
  - Vite proxy path
- The previously observed Chinese freeform integration gap has been closed.

## Remaining Recommendations

These are recommendations, not blockers for accepting the current work:

1. Add parser-version metadata into structured logs or parse payloads so fallback/failed rates can be analyzed by parser revision.
2. Keep multilingual expansion incremental and data-driven rather than broadening the signal pack aggressively in one step.
3. Preserve the current shared signal baseline when the schema-first LLM parser path is introduced, so deterministic and LLM outputs stay comparable.

## Acceptance Conclusion

This parser-quality expansion can be treated as a stable milestone.

It improves real-world usability, especially for Chinese freeform inputs, while preserving:
- MVP boundaries
- asynchronous ingest behavior
- state replayability assumptions
- frontend/backend contract stability
