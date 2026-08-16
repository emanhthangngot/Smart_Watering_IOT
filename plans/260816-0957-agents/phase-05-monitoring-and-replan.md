---
phase: 5
title: "Monitoring and replan"
status: pending
priority: P1
effort: "3h"
dependencies: [4]
---

# Phase 5: Monitoring and replan

## Overview

Assumption evaluator (A1-A6, §6.1 table), idempotent invalidation, debounce,
one open re-plan per assumption (§10.2), and the rain/external-water path
(§9.5).

## Requirements

- Functional: on new batch, only re-evaluate assumptions actually touched
  by changed readings — never re-run the full pipeline per message.
  Invalidation key `(planRevisionId, assumptionId, triggeringEvidenceVersion)`
  is idempotent; debounce repeated readings within one observation window;
  max one open re-plan per assumption.
- Non-functional: `soil_rise_pump_off` firing invalidates A6 and defers or
  cancels pending irrigation schedules, with a reason attached.

## Architecture

This module calls into M4's tool layer (`tools/`) only for inspection-task
creation on invalidation — never directly mutates schedule/action state
itself (M4 owns that side effect).

## Related Code Files

- Create: `agents/monitor.py` (assumption evaluator + debounce),
  `agents/replan.py` (V(n+1) creation)

## Implementation Steps

1. `agents/monitor.py`: on World State update, find touched assumptions,
   evaluate predicates from the §6.1 table, apply idempotency key +
   debounce.
2. On invalidation: append evidence, mark `INVALIDATED`, suspend plan,
   notify Coordinator, cap at one open re-plan per assumption.
3. `agents/replan.py`: creates V(n+1) via the Planner (phase 03), never
   mutates Vn.
4. Wire A6 (`soil_rise_pump_off`) to defer/cancel pending schedules via
   M4's tool layer.

## Success Criteria

- [ ] Replaying the same batch twice does not create a duplicate invalidation or a duplicate re-plan.
- [ ] A 1Hz stream of repeated stale readings produces at most one suspension per debounce window, not hundreds.
- [ ] At most one open re-plan exists per assumption at any time (assert in a stress test).
- [ ] Soil-rise-while-pump-off fixture defers/cancels the pending schedule with a reason.

## Risk Assessment

§10.2's explicit warning: without idempotency + debounce + the one-re-plan
cap, a 1Hz stream produces "hàng trăm suspension" — this is a load test,
not just a unit test; include a stress fixture with rapid repeated batches.
