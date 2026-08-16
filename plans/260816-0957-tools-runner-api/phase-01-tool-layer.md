---
phase: 1
title: "Tool layer"
status: pending
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: Tool layer (INV-6)

## Overview

The single choke point for every side-effecting action (§7.3). Checks plan
status, tier, approval + `revisionHash`, evidence requirement, and
idempotency **before** calling anything. Downgrade ladder on refusal, max 2
hops.

## Requirements

- Functional: `idempotency_key = sha1(planRevisionId | tool | canonical(params))`.
  Retry or duplicate telemetry never creates a duplicate schedule/task.
  Refusal downgrade: `create_irrigation_schedule` →
  `propose_irrigation_plan` → `create_inspection_task` (always allowed),
  max 2 hops — never "nothing we can do."
- Non-functional: Planner/Diagnosis/Resource never call this layer's
  underlying APIs directly — only through the permission check.

## Architecture

`ToolPermission` records (from `contracts.py`) declare `allowed_plan_statuses`,
`min_tier`, `approval_required` per tool — this module enforces them, not
individual callers.

## Related Code Files

- Create: `tools/permission.py`, `tools/idempotency.py`, `tools/downgrade.py`,
  `tools/irrigation.py` (the actual tool implementations)

## Implementation Steps

1. `tools/idempotency.py`: key computation + a dedup check against a store
   (via `store/db.py`, read/write through M1's storage layer).
2. `tools/permission.py`: given a `ToolPermission` + current plan/tier/
   approval, allow or deny before any side effect executes.
3. `tools/downgrade.py`: the 2-hop ladder, invoked on denial.
4. `tools/irrigation.py`: the actual side-effecting calls, gated by the
   above.

## Success Criteria

- [ ] Calling a tool with an expired/mismatched `revisionHash` is denied, no side effect occurs.
- [ ] Same `(planRevisionId, tool, params)` called twice produces one schedule, not two.
- [ ] Denied `create_irrigation_schedule` downgrades to `propose_irrigation_plan`, then `create_inspection_task` if still denied — never returns "no action."
- [ ] `tests/invariants/test_inv_06.py` passes.

## Risk Assessment

This is the safety backstop against prompt injection or a misbehaving
agent (§16 "Bypass safety bằng prompt") — treat any path that reaches a
side effect without going through `tools/permission.py` as a critical bug.
