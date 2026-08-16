---
phase: 6
title: "Fixtures and eval"
status: pending
priority: P1
effort: "2h"
dependencies: [1]
---

# Phase 6: Fixtures and eval

## Overview

F1–F4 fixtures (§4.4) as the frozen test contract M2 builds against, plus
`eval/score_scenarios.py` (§3.7) for offline scenario scoring — isolated
from the runtime decision path.

## Requirements

- Functional: F1 `bundle_healthy` → all FRESH, expect DCS 1.00/AUTO. F2
  `bundle_stale` → expect DCS 0.80/PROPOSE. F3 `bundle_broken` → expect cap
  0.40/INVESTIGATE. F4 `bundle_stuck` → expect cap 0.40/INVESTIGATE (the
  critical case: fresh-looking data, still must not be AUTO).
- Non-functional: `eval/score_scenarios.py` imports nothing from `trust/`
  or `agents/` (INV-9) — verified by a grep test, not just code review.

## Architecture

Fixtures are static JSON bundles matching the real payload shape, with the
exact numbers from §4.4 baked in so M2's `test_trust.py` can assert exact
tier output.

## Related Code Files

- Create: `fixtures/f1_bundle_healthy.json` .. `fixtures/f4_bundle_stuck.json`
- Create: `eval/score_scenarios.py`
- Create: `tests/data_plane/test_fixture_shapes.py`
- Create: `tests/invariants/test_inv_09.py` (grep guard: `scenario` never
  appears in `trust/`, `agents/`, `graph/`)

## Implementation Steps

1. Author F1-F4 as JSON fixtures with §4.4's exact readings.
2. `eval/score_scenarios.py`: segment by `scenario`, compute
   `detected`/`detection_lag` for non-NORMAL segments, `false_alarm` for
   NORMAL segments — reads replay logs only, no runtime imports.
3. `tests/invariants/test_inv_09.py`: grep `trust/`, `agents/`, `graph/`
   source for the literal string `scenario`, fail if found.

## Success Criteria

- [ ] 4 fixture files exist, valid JSON, match payload shape.
- [ ] `test_inv_09.py` passes (grep finds zero matches outside allowed files).
- [ ] `eval/score_scenarios.py` has no `import trust` / `import agents` anywhere in its module or transitive imports.

## Risk Assessment

None beyond what §16 already tracks (accidental `scenario` leak) — this
phase is the enforcement mechanism for that exact risk.
