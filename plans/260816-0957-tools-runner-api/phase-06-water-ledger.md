---
phase: 6
title: "Water ledger"
status: pending
priority: P1
effort: "2h"
dependencies: [1]
---

# Phase 6: Water ledger (INV-2)

## Overview

Daily drawdown constraint enforcement + reconciliation (§8) — makes
"water is a scarce budget" a real accounting fact, not just an
instantaneous check.

## Requirements

- Functional: sum of `planned_drawdown_pct` for all still-active plans
  today ≤ `level_now − safe_reserve_pct` (Resource, M3, enforces this as a
  blocking objection — this phase provides the ledger it reads).
  Reconciliation after each window: compare `observed_tank_drawdown_pct`
  vs `observed_flow_integral` → `MATCH | UNDER_DELIVERED | OVER_DRAWN |
  INCONCLUSIVE`.
- Non-functional: units stay `%` tank level and pump minutes — never
  convert to liters unless `TANK_CAPACITY_L` is an explicit, UI-visible
  config assumption.

## Architecture

`water_ledger` table (schema owned by M1, generated from registry) is
written here on schedule close (from phase 02's `CLOSING` transition) and
read by M3's Resource agent for the daily constraint.

## Related Code Files

- Create: `verify/ledger.py`

## Implementation Steps

1. `verify/ledger.py`: write a `water_ledger` row on every schedule window
   close, with planned vs observed drawdown/flow-integral/pump-minutes.
2. Reconciliation function: `MATCH`/`UNDER_DELIVERED`/`OVER_DRAWN` given a
   configurable tolerance; `INCONCLUSIVE` when required readings are
   STALE/SUSPECT.
3. Expose a query for "sum of active plans' planned drawdown today" for
   M3's Resource agent to enforce the constraint.

## Success Criteria

- [ ] A window where observed drawdown/flow-integral ratio diverges beyond tolerance → `UNDER_DELIVERED`/`OVER_DRAWN`, feeding evidence to Diagnosis, not just a log line.
- [ ] Missing/stale tank reading during a window → `INCONCLUSIVE`, never guessed.
- [ ] No liter conversion appears anywhere unless `TANK_CAPACITY_L` is set and displayed as an assumption.
- [ ] `tests/invariants/test_inv_02.py` passes.

## Risk Assessment

§8's warning is explicit: "mọi con số tiết kiệm là bịa" without this
ledger — treat any UI or report claiming water savings without a ledger
entry backing it as a defect to reject in review (mostly relevant when M5
consumes this data).
