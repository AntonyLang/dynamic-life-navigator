# Next Phase Plan: Schema-First Structured Parsing

This document defines the next engineering phase after the deterministic multilingual parser expansion.

## Summary

The next phase should focus on schema-first structured parsing and profiling, with deterministic rules kept as the fallback and control baseline.

This phase should:
- preserve the current API surface
- preserve ack-first ingest behavior
- keep heavy parsing off the synchronous request path
- avoid real push delivery or replay tooling work in parallel

## Goals

1. Introduce a schema-bound internal parsing contract that can support both deterministic and LLM-backed parsing.
2. Add an LLM parser path behind configuration, without making the system depend on it for correctness.
3. Keep deterministic parsing as a fallback and as the comparison baseline.
4. Preserve current worker-off and worker-on behavior from the frontend's perspective.

## Non-Goals

This phase should not include:
- real push delivery
- replay / rebuild operator tooling
- major frontend redesign
- multimodal input expansion
- changes to public endpoint names or response shapes

## Proposed Scope

### 1. Add schema-bound parser DTOs
- Introduce explicit internal Pydantic models for:
  - parser output
  - profile output
  - validation errors / fallback reasons
- Keep these DTOs aligned with the current `ParsedImpact` structure where possible.
- Preserve the existing downstream state patching contract so the recommendation loop does not need to be rewritten.

### 2. Add a parser provider interface
- Introduce a small provider boundary such as:
  - deterministic parser provider
  - structured LLM parser provider
- Selection should be configuration-driven.
- The deterministic provider remains the default.

### 3. Add schema-first LLM parsing behind a flag
- New parsing should use:
  - schema-bound output
  - runtime validation
  - retry-on-invalid-output
  - deterministic fallback on failure
- Invalid or partial outputs must never corrupt `user_state`.
- LLM parsing must remain worker-only, never on the synchronous ingest path.

### 4. Add parse metadata for observability
- Extend parse metadata with fields such as:
  - `parser_version`
  - `prompt_version`
  - `model_name`
  - `fallback_reason`
- Keep these in structured logs and/or `parsed_impact` metadata.
- This should help us measure:
  - success / fallback / failed ratios
  - LLM-valid vs invalid output rates
  - drift between deterministic and LLM outcomes

### 5. Mirror the same shape for node profiling
- Reuse the same provider-style design for async node profiling.
- Deterministic profiling stays as the safe baseline.
- Structured LLM profiling should only backfill fields after validation.

## Implementation Order

### Step 1: internal schemas and provider boundary
- add parser DTOs
- add deterministic provider wrapper
- leave runtime behavior unchanged

### Step 2: structured parser stub
- add provider interface for LLM parsing
- add config flags and no-op/stub provider
- keep deterministic as default

### Step 3: validated LLM parser integration
- implement schema-first parsing path
- validate output
- retry once or twice on invalid output
- fall back to deterministic output if still invalid

### Step 4: profiling parity
- apply the same pattern to async node profiling
- keep node creation behavior unchanged

### Step 5: metrics and comparison logs
- record parse version / prompt version / model name
- log fallback reasons
- make it easy to compare deterministic vs LLM output behavior

## Acceptance Criteria

The phase is complete when:

1. External API contracts remain unchanged.
2. Ingest remains ack-first in both worker-off and worker-on modes.
3. Structured parser outputs are validated before state updates.
4. Invalid LLM output cleanly falls back to deterministic parsing.
5. Existing multilingual deterministic coverage still works if LLM parsing is disabled.
6. The backend suite stays green.
7. The frontend integration baseline stays green.

## Verification Plan

### Backend
- keep the full backend suite passing
- add tests for:
  - valid structured parse
  - invalid structured parse with retry
  - fallback to deterministic parse
  - worker-off structured parse flow
  - worker-on structured parse flow

### Frontend
- re-run:
  - `npm.cmd run test`
  - `npm.cmd run build`
- confirm the frontend still sees the same state/recommendation contracts

### Manual smoke
- repeat:
  - chat -> state convergence
  - `/pull`
  - feedback
  - `/brief`
- verify behavior remains stable from the UI point of view

## Priority After This Phase

Once schema-first structured parsing is in place, the next priorities should remain:

1. real push delivery with audit outcomes
2. replay / rebuild tooling over `event_logs`
3. broader deterministic and multilingual fallback coverage where still needed
