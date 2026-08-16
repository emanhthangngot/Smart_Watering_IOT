---
phase: 5
title: "Simulator"
status: pending
priority: P2
effort: "3h"
dependencies: [1]
---

# Phase 5: Simulator

## Overview

Causal `WorldState` simulator for `ACTUATION_TARGET=sim` mode (§9.2).
Needed for M2's water-balance testing and the closed-loop demo, but not
on the critical path to G1.

## Requirements

- Functional: single shared `WorldState` — pump on moves tank down **and**
  soil up together, never independent per-device randomness. Fault flags:
  `pump_no_effect`, `tank_leak`, `sensor_stuck`, `device_offline`.
- Non-functional: same batch/publish shape as the real broker so
  `ingest/normalize.py` cannot tell the difference.

## Architecture

Sim publishes batches in the same JSON shape as `plans/input_format.txt`.
Runner (M4, phase 02) sends commands into the sim in `sim` mode; sim state
updates feed back into the next published batch — the actual closed loop.

## Related Code Files

- Create: `sim/world.py`, `sim/faults.py`, `sim/publisher.py`

## Implementation Steps

1. `sim/world.py`: shared state (tank level, soil moisture, flow, etc.)
   with a `tick()` that applies pump-on physics.
2. `sim/faults.py`: fault flag application (leak, stuck, offline, no-effect).
3. `sim/publisher.py`: emits batches matching the real payload shape at a
   configurable cadence.

## Success Criteria

- [ ] Pump on for N ticks → tank level decreases AND soil moisture increases in the same run.
- [ ] `sensor_stuck` flag on `SOIL_01` → identical value for ≥ 12 consecutive batches while TANK/PUMP still move (feeds F4 fixture).
- [ ] `device_offline` flag → device absent from `devices[]` for the flagged duration.

## Risk Assessment

Low priority relative to G0/G1 — sequence after phase 02 if time is tight;
M2 can test against F1-F4 static fixtures (phase 06) without the live sim.
