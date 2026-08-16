---
phase: 2
title: "Hard-fail / soft-penalty rules"
status: pending
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Hard-fail / soft-penalty rules

## Overview

Implement §4.3's separation: hard-fails flip a reading's status to SUSPECT
(drops it from F and C); soft rules only penalize K. This is the fix for
v4's biggest defect (F4: a stuck sensor must never look AUTO).

## Requirements

- Functional: hard-fails — `source_not_ok` (`status != "ok"`),
  `out_of_range` (physical bounds per metric), `stuck_at` (bit-identical
  ≥ `stuck_batches` (12) **and** a correlated in-scope signal moved).
  Soft rules — `pump_on_soil_flat` (−0.35), `tank_drain_no_pump` (−0.30),
  `flow_without_tank_drop` (−0.25), `power_without_flow` (−0.30),
  `soil_rise_pump_off` (−0.15).
- Non-functional: every rule function is pure, never raises — missing data
  makes `val()`/`delta()` return `None`, rule returns `False`.

## Architecture

One file per rule under `trust/rules/`, discovered by a registry function
— never a shared `RULES = [...]` list literal (merge-safety, §2).
Deliberately excluded: soil-vs-air temperature fixed-threshold rule (§4.3
"Rule bị loại bỏ có chủ ý") — do not add it.

## Related Code Files

- Create: `trust/rules/source_not_ok.py`, `trust/rules/out_of_range.py`,
  `trust/rules/stuck_at.py`, `trust/rules/pump_on_soil_flat.py`,
  `trust/rules/tank_drain_no_pump.py`, `trust/rules/flow_without_tank_drop.py`,
  `trust/rules/power_without_flow.py`, `trust/rules/soil_rise_pump_off.py`,
  `trust/rules/registry.py` (discovery)

## Implementation Steps

1. Write each rule as its own module, signature `(bundle, windows) -> bool`.
2. `trust/rules/registry.py`: `HARD_FAILS`, `SOFT_RULES` built by
   introspecting `trust/rules/*.py`, not a hand-maintained list.
3. Wire hard-fail rules to flip reading status to SUSPECT (feeds phase 1's
   state machine) rather than only subtracting from K.

## Success Criteria

- [ ] `stuck_at` on F4 fixture (SOIL_01.soil_moisture bit-identical 12 batches, TANK/PUMP moving) fires; on a fixture where nothing else moves, does not fire.
- [ ] Every rule called with an empty/missing-data bundle returns `False`, never raises.
- [ ] Soil-vs-air fixed-threshold temperature rule does not exist anywhere in `trust/rules/`.

## Risk Assessment

`stuck_batches = 12` and the correlated-signal requirement are load-bearing
for F4 — verify against the exact F4 fixture from `feat/data-plane` phase
06 before merging, not against a hand-built approximation.
