---
phase: 4
title: "Grounding and graph"
status: pending
priority: P1
effort: "3h"
dependencies: [3]
---

# Phase 4: Grounding and graph

## Overview

`assert_grounded` rejects any plan whose `evidenceRefs` aren't backed by
real `readingId#metric` values in the bundle; Evidence Graph edges written
at the 5 join points; `/explain` BFS (§11.1).

## Requirements

- Functional: `assert_grounded(plan, bundle)` — any `evidenceRef` not in
  `{id#metric for readings in bundle}` → reject `UngroundedClaim`, retry
  up to 2 times, then fall back to the deterministic allocator's own
  reasons (no LLM phrasing on that attempt).
- Non-functional: `edges(src, dst, rel, trace_id)` written at exactly the 5
  points in the §11.1 table — no other module writes to `edges`.

## Architecture

`/explain/{decisionId}` does a BFS backward over `{supports, derived_from}`
to reading nodes, returning `age_s` **at decision time** (from the trust
snapshot + `createdFromStateVersion`), not current age.

## Related Code Files

- Create: `graph/grounding.py`, `graph/edges.py`, `graph/explain.py`

## Implementation Steps

1. `graph/grounding.py`: `assert_grounded`, retry-then-fallback wrapper
   around the Planner's LLM call from phase 03.
2. `graph/edges.py`: `write_edge(src, dst, rel, trace_id)` — called from
   exactly the 5 places in the §11.1 table (Planner, Diagnosis/RCA, Action,
   Verify, Monitor — the last two are M4's calls into this module).
3. `graph/explain.py`: BFS query + `age_s`-at-decision-time resolution.

## Success Criteria

- [ ] A plan with a fabricated `evidenceRef` is rejected before it reaches Coordinator.
- [ ] After 2 rejected retries, the system produces a plan via the deterministic allocator, not an error.
- [ ] `/explain` on a real decision returns a reading node with `age_s` matching the trust snapshot at that decision's `createdFromStateVersion`, not `now()`.
- [ ] `tests/invariants/test_inv_04.py` — every decision has ≥1 edge to a real reading, no dangling edges.

## Risk Assessment

INV-4 is the invariant this phase directly implements — treat any dangling
edge found in testing as a phase-04 defect, not an acceptable gap.
