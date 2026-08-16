---
phase: 3
title: "Planner"
status: pending
priority: P1
effort: "4h"
dependencies: [2]
---

# Phase 3: Planner

## Overview

Deterministic allocator is the primary path; LLM only phrases the plan
into assumptions/reasons (§7.1). LLM dead or out of quota → plan still
produced. Plan object per §6, immutable versions, lineage.

## Requirements

- Functional: deterministic allocator ranks by soil-moisture urgency,
  splits pump minutes under tank/no-overlap/hour-window constraints —
  computed **before** any LLM call. Plan schema exactly matches §6's JSON
  skeleton (`planRevisionId`, `planLineageId`, `version`,
  `revisionOfPlanRevisionId`, assumptions A1-A6, `waterBudget`, etc).
- Non-functional: V1 is never mutated; a challenge moves it to
  `CHALLENGED` history, a new revision object is created for V2.

## Architecture

The allocator is not a fallback/safety-net — it is the main path (§7.1:
"không phải lưới an toàn"). The LLM call wraps it, never replaces it.

## Related Code Files

- Create: `agents/allocator.py` (deterministic core), `agents/planner.py`
  (LLM phrasing wrapper), `prompts/planner.py`

## Implementation Steps

1. `agents/allocator.py`: pure deterministic ranking + time-slicing under
   constraints — no LLM call anywhere in this file.
2. `agents/planner.py`: calls the allocator first, then (if LLM available)
   asks it to phrase assumptions/reasons from the allocator's output —
   never asks the LLM to invent numbers.
3. `prompts/planner.py`: prompt template, explicitly instructed to only
   phrase given facts, never compute.

## Success Criteria

- [ ] With the LLM call mocked to raise/timeout, `agents/planner.py` still returns a valid Plan object.
- [ ] Plan object round-trips through `contracts.py` validation with all §6 fields present.
- [ ] Two calls to `agents/planner.py` for the same lineage never mutate the first `PlanRevision` — only create new objects.

## Risk Assessment

The single biggest architecture risk in the whole design (§16: "Trượt về
pipeline LLM tuyến tính" / "LLM chết hoặc bịa evidence") — this phase is
where that risk is either closed or reintroduced. Test the LLM-down path
explicitly, don't just assume it degrades gracefully.
