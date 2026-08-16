---
phase: 5
title: "Trace and responsive"
status: pending
priority: P1
effort: "2h"
dependencies: [2, 3, 4]
---

# Phase 5: Trace and responsive

## Overview

Trace/explain view (`GET /explain/{decisionId}`, `GET /timeline/{traceId}`)
and a final responsive pass across every screen at 390px — this is gate G4's
UI half.

## Requirements

- Functional: trace view renders the BFS lineage from `/explain` (reading
  age at decision time, not current age) and the `/timeline` event
  sequence.
- Non-functional: Farm State, Plan Detail, Approval, Inspection Tasks,
  Trace all intact — no horizontal scroll, no clipped controls — at 390px.

## Architecture

Consumes `GET /explain/{decisionId}`, `GET /timeline/{traceId}` (M3/M4).

## Related Code Files

- Create: `frontend/app/trace/`, `frontend/app/timeline/`

## Implementation Steps

1. Trace view: render the evidence lineage graph/list from `/explain`,
   showing `age_s` as captured at decision time.
2. Timeline view: chronological event list from `/timeline`.
3. Responsive pass: verify every screen from phases 02-04 plus this one at
   390px width — fix any overflow found.

## Success Criteria

- [ ] Trace view shows reading age-at-decision-time, verifiably different from current age in a test fixture where time has passed.
- [ ] All 5 screens (Farm State, Plan Detail, Approval, Inspection Tasks, Trace) render with zero horizontal scroll at 390px — this is G4's manual/automated check.

## Risk Assessment

Low — the main failure mode is a component that looks fine on desktop and
breaks at 390px; test this phase explicitly at that width, not just "mobile
responsive" in general.
