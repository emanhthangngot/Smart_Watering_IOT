---
phase: 3
title: "Verification"
status: pending
priority: P1
effort: "2h"
dependencies: [2]
---

# Phase 3: Verification

## Overview

Two separate verification layers (§10.1): Action (did the API/tool create
the right entity?) and Outcome (did reality match expectation?). `none`
mode is observational-only (§9.3).

## Requirements

- Functional: Action Verification = POST result + GET read-back, id/status/
  params match. Outcome Verification = MQTT window + expected-vs-actual
  (via M2's `trust/expected.py`) + water-balance + ledger. `INCONCLUSIVE`
  is a first-class result, never coerced to `PASS`.
- Non-functional: in `none` mode, outcome verification only observes —
  never assumes control it doesn't have.

## Architecture

Action PASS does not imply Outcome PASS — both are recorded as separate
`Verification` records (from `contracts.py`).

## Related Code Files

- Create: `verify/action.py`, `verify/outcome.py`

## Implementation Steps

1. `verify/action.py`: POST + read-back comparison, produces `PASS`/`FAIL`.
2. `verify/outcome.py`: reads M2's `trust/expected.py` divergence output +
   ledger reconciliation, produces `PASS`/`FAIL`/`INCONCLUSIVE`.
3. Explicit `none`-mode branch: no expectation of control, `INCONCLUSIVE`
   when no evidence of pump activity in the window.

## Success Criteria

- [ ] Schedule created correctly but pump underperforms → Action PASS, Outcome FAIL, both recorded.
- [ ] `none` mode with no observed pump activity in window → `INCONCLUSIVE`, not `PASS`.
- [ ] No code path anywhere maps `INCONCLUSIVE` to `PASS`.

## Risk Assessment

§9.3 calls this "điểm trung thực quan trọng nhất" — treat any shortcut
that collapses `INCONCLUSIVE` into `PASS` for a demo as a hard defect, not
a UX nicety.
