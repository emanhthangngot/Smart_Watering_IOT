---
phase: 3
title: "DCS and tier"
status: pending
priority: P1
effort: "3h"
dependencies: [1, 2]
---

# Phase 3: DCS and tier (gate G2)

## Overview

`DCS = 0.45F + 0.35C + 0.20K`, caps, per-scope independence, hysteresis +
dwell (§4.2, §4.5). This phase is gate G2: F1-F4 must produce the four
documented tiers exactly.

## Requirements

- Functional: caps override — required metric SUSPECT/OFFLINE/MISSING or
  freshness 0 → DCS ≤ 0.40; K < 0.50 → DCS ≤ 0.55. Tier thresholds: AUTO
  ≥ 0.85 (raise) / < 0.80 (drop), PROPOSE ≥ 0.50 (raise) / < 0.45 (drop).
  Raise requires ≥ 2 consecutive evaluations over threshold **and** ≥ 60s
  since last tier change; drop is immediate, no dwell.
- Non-functional: computed independently per scope (`irrigation_plan`,
  `session_check`, `tank_quality`); snapshot records
  F/C/K/cap-applied/rules-fired/`dcsPolicyVersion`.

## Architecture

`trust_snapshots` table (owned by `store/`, M1) is written here via
`store/db.py`. Metric required and STALE/SUSPECT/OFFLINE blocks the
dependent action even when scope DCS is high — tier is necessary, not
sufficient (§4.5).

## Related Code Files

- Create: `trust/score.py` (DCS formula + caps), `trust/tier.py`
  (hysteresis + dwell state machine), `trust/reasons.py` (human-readable
  explanation of the verdict)
- Create: `tests/trust/test_fixtures.py` (the G2 gate test)

## Implementation Steps

1. `trust/score.py`: F/C/K aggregation per scope from phase 1+2 outputs,
   apply caps.
2. `trust/tier.py`: hysteresis state machine per scope, persisted across
   evaluations (needs last-tier-change timestamp + evaluation streak).
3. `trust/reasons.py`: assemble the human-readable "why this tier" string
   for UI/explain use.
4. `tests/trust/test_fixtures.py`: load F1-F4 from `feat/data-plane`,
   assert exact tier output.

## Success Criteria

- [ ] `pytest tests/trust/test_fixtures.py` — F1→AUTO(1.00), F2→PROPOSE(0.80), F3→INVESTIGATE(cap 0.40), F4→INVESTIGATE(cap 0.40).
- [ ] DCS oscillating around 0.85 across consecutive evaluations does not flap tier more than once per dwell window.
- [ ] `dcsPolicyVersion` + F/C/K + cap + fired-rules all present in every snapshot.

## Risk Assessment

This is the highest-value correctness gate in the whole trust engine — F4
is specifically the regression test for v4's worst bug (stuck sensor still
AUTO). Do not relax the cap logic to make a fixture pass; if a fixture
fails, the bug is in the formula, not the fixture.
