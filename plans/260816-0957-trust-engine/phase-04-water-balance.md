---
phase: 4
title: "Water-balance"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 4: Water-balance

## Overview

§5 direction/ratio physical reasoning: pump-on should mean tank down and
soil up together, at a learned baseline ratio. Deterministic evidence for
Diagnosis (M3), not an LLM inference.

## Requirements

- Functional: implement the 5 diagnosis branches in §5 (pipe leak, flow/tank
  mismatch, dry-run/clogged filter, external water, ratio drift >2σ).
  Baseline `ratio` fit from 2-3 early irrigation sessions or 10-15 min
  warm-up.
- Non-functional: pH stays advisory-only in `tank_quality`, never gates
  `irrigation_plan` (§5.1) — deviation measured from the observed baseline
  (≈10), not textbook agronomic bounds.

## Architecture

Output is deterministic evidence consumed by M3's Diagnosis agent — this
module never calls an LLM and never emits a plan action directly.

## Related Code Files

- Create: `trust/physics.py` (ratio baseline fit + the 5 diagnosis branches)

## Implementation Steps

1. `trust/physics.py`: baseline ratio estimator (warm-up window).
2. Implement each of the 5 branches from §5 as a named diagnosis function
   returning structured evidence (not free text).
3. pH check: `0 ≤ ph ≤ 14` hard-fail only (physical impossibility); all
   other pH signal is deviation-from-observed-baseline, advisory.

## Success Criteria

- [ ] Given pump-on + tank-down + soil-flat fixture → returns `pipe_leak`-class evidence, not silence.
- [ ] `ph = 10` (payload's real NORMAL baseline) never triggers any irrigation-blocking evidence.
- [ ] Baseline ratio warm-up completes within 10-15 min of simulated sessions in a test.

## Risk Assessment

§5.1's warning is explicit: a textbook pH threshold (5.5-7.5) would block
irrigation forever at this farm's real baseline. Verify no constant in this
file falls inside that trap — cross-check against `test_inv_10.py` (M1's
baseline-threshold guard).
