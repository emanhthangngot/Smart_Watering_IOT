---
phase: 5
title: "Expected-vs-actual"
status: pending
priority: P2
effort: "2h"
dependencies: [4]
---

# Phase 5: Expected-vs-actual

## Overview

Narrow predicate model for flow/soil response divergence (§10.3), feeding
Outcome Verification (M4) and assumption invalidation (M3). Not a
Ghost Farm digital twin — P1/P2 scope only extends this later.

## Requirements

- Functional: given an active plan's expected flow/soil trajectory, compute
  divergence against actual readings; divergence must reference a specific
  `assumptionId`, never a bare number.
- Non-functional: works directly on MQTT-derived readings, no dependency on
  a future Ghost Farm model.

## Architecture

Consumed by M3's assumption evaluator (A1-A6) and M4's Outcome Verification
— both read-only relative to this module.

## Related Code Files

- Create: `trust/expected.py`

## Implementation Steps

1. `trust/expected.py`: given `ExpectedOutcome` (from `contracts.py`) and a
   window of readings, compute observed vs expected, return divergence +
   the `affectedAssumptionId`.

## Success Criteria

- [ ] Divergence result always carries a non-empty `assumptionId`.
- [ ] Flow drop fixture (13.9 → 4.5 L/min, power unchanged) produces a
      divergence result usable directly by N2's scenario test.

## Risk Assessment

Low — this is a thin predicate layer; main risk is scope creep toward a
full digital twin, explicitly out of scope per §10.3.
