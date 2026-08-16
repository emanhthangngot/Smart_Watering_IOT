---
phase: 5
title: "Integration gates"
status: pending
priority: P1
effort: "n/a — process document"
dependencies: [1, 2, 4]
---

# Phase 5: Integration gates

## Overview

G0–G5 with the exact command each gate runs and who signs off, adapted
from `plan.md` §13.3's sync points.

## Requirements

- Functional: every gate has a command that exits 0/non-zero, not a
  subjective judgment call.
- Non-functional: gate results are visible on `dev` (CI output or pasted
  into the PR per the PR template).

## Architecture

| Gate | Condition | Command | Signs off |
|---|---|---|---|
| G0 | `contracts.py` + registry + F1-F4 merged and frozen | `python -c "from registry.specs import wsum; assert wsum('irrigation_plan')==13"` | M1 owner + integrator |
| G1 | `schema.sql` applied, one real batch in 6 tables, read back via `readings_all` | `python -m store.smoke_test` (M1 writes this in phase-02) | M1 owner |
| G2 | Trust engine returns the 4 expected tiers on the 4 fixtures | `pytest tests/trust -k "f1 or f2 or f3 or f4"` | M2 owner |
| G3 | Each owner demos their slice for 60s against `dev`; contract mismatches fixed on the spot | manual, logged in `dev` plan.md | all owners |
| G4 | Kill `SOIL_01` → OFFLINE after 3 batches → cap 0.40 → INVESTIGATE → inspection task → chip changes at 390px | `pytest tests/invariants -k n3_scenario` | M1+M2+M3+M5 |
| G5 | N1-N4 (`plan.md` §14) pass as automated replay, 5 consecutive clean runs | `pytest tests/ -m "not slow" && for i in 1 2 3 4 5; do pytest tests/scenarios; done` | integrator |

## Related Code Files

- Referenced: `plan.md` §13.3, §14
- Created by owners as they build: `store/smoke_test.py` (M1),
  `tests/trust/test_fixtures.py` (M2), `tests/invariants/test_n3_scenario.py`,
  `tests/scenarios/` (N1-N4, shared)

## Implementation Steps

1. Each gate's command is written by the owning branch as part of its own
   phases (cross-referenced above), not invented separately here.
2. Integrator runs the gate command before allowing the corresponding merge
   in phase-04's order table.
3. G5 result gates `dev → main`.

## Success Criteria

- [ ] All 6 gate commands exist and are runnable (accumulated as branches land).
- [ ] G5 has been run 5 consecutive times clean before any `dev → main` merge.

## Risk Assessment

Risk: a gate command doesn't exist yet when its merge is attempted.
Mitigation: phase-04's merge order table names the exact gate per merge —
integrator refuses the merge if the command is missing rather than
approving on verbal confirmation.
