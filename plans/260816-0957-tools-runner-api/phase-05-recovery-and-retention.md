---
phase: 5
title: "Recovery and retention"
status: pending
priority: P1
effort: "2h"
dependencies: [2, 4]
---

# Phase 5: Recovery and retention

## Overview

Startup scan for non-terminal records (§10.4) so a restart never leaves a
zombie plan holding a pump lock; hourly batched retention + rollup
(§11.4).

## Requirements

- Functional: on startup, scan for schedule `RUNNING` past its window
  (→ `CLOSING` + late verification), `PENDING` past grace (→ `MISSED`),
  plan `EXECUTING` (→ reattach monitor, re-evaluate all assumptions),
  expired approvals (→ revoke, plan `EXPIRED`), actions missing
  verification (→ re-queue, idempotent).
- Non-functional: retention deletes in small batches
  (`delete ... where epoch < $1 limit 5000`) to avoid long locks blocking
  ingest; `edges`, `plans`, `actions`, `verifications`, `water_ledger`,
  `audit_log` are never deleted.

## Architecture

Runs once at process startup, before the schedule runner (phase 02) and
agent monitor (M3 phase 05) start accepting new work.

## Related Code Files

- Create: `api/recovery.py` (startup scan), `store/retention.py` (hourly
  job — coordinate path ownership with M1 since it touches `store/`;
  confirm on `dev` before creating if M1 already claimed this file)

## Implementation Steps

1. `api/recovery.py`: implements the 5-case table from §10.4, called at
   app startup before serving traffic.
2. `store/retention.py`: hourly batched delete for sensor tables (7-day
   raw retention) + rollup into `readings_hourly`; never touches audit
   trail tables.

## Success Criteria

- [ ] Simulated restart with a `RUNNING` schedule past its window → `CLOSING` + `late_verification` flag, not silently dropped.
- [ ] Simulated restart with `EXECUTING` plan → monitor reattached, assumptions re-evaluated immediately.
- [ ] Retention batch delete never blocks a concurrent ingest write beyond the batch's own transaction.

## Risk Assessment

`store/retention.py` sits in M1's owned directory (`store/`) — check with
the integrator on `dev` before creating it under M4; if M1 already scaffolds
retention hooks, extend those instead of adding a competing file.
