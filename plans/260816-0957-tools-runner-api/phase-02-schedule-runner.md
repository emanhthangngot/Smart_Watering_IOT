---
phase: 2
title: "Schedule runner"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: Schedule runner (INV-1, INV-2, INV-3)

## Overview

5s tick loop, transactional claim, no catch-up, one `RUNNING` schedule per
pump enforced at the DB layer (§9.1).

## Requirements

- Functional: `PENDING → RUNNING → CLOSING → DONE|FAILED`; `MISSED` if
  `now > start + grace` (default 2 min), no catch-up run; `CANCELLED` on
  plan `SUSPENDED`. Claim via `UPDATE ... WHERE status='PENDING'`
  transaction — two workers never claim the same schedule.
- Non-functional: unique partial index `(pump_id) WHERE status='RUNNING'`
  — enforced by Postgres, not application-level assertion.

## Architecture

Separate async loop from the agent pipeline (§9.1) — does not call an LLM,
does not block on agent decisions mid-tick.

## Related Code Files

- Create: `schedule/runner.py`, `schedule/claim.py`
- Modify (append, coordinate with M1): schema needs the partial unique
  index — request via `store/gen_ddl.py` if not already present from M1's
  phase 02; do not hand-edit `store/schema.sql` directly (M1-owned,
  generated file).

## Implementation Steps

1. `schedule/claim.py`: transactional `UPDATE` claim, single source of
   truth for state transitions.
2. `schedule/runner.py`: 5s tick loop driving PENDING→RUNNING→CLOSING→DONE.
3. Coordinate with M1 to confirm the partial unique index exists on
   `(pump_id) WHERE status='RUNNING'` before relying on it.
4. `grace` and no-catch-up are policy constants — document them visibly,
   don't bury in a config file nobody reads.

## Success Criteria

- [ ] Two concurrent claim attempts on the same PENDING row → exactly one wins.
- [ ] A second schedule for a pump already `RUNNING` fails at insert time (DB constraint), not caught after the fact.
- [ ] `PENDING` schedule past `grace` → `MISSED`, no run attempted.
- [ ] `tests/invariants/test_inv_01.py`, `test_inv_02.py`, `test_inv_03.py` pass.

## Risk Assessment

If the unique partial index isn't actually in `store/schema.sql`, INV-3
degrades to an application-level race — verify the index exists in the
real generated schema before marking this phase done, don't assume.
