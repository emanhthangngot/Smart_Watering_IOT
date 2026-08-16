---
phase: 1
title: "Contracts and registry"
status: pending
priority: P1
effort: "3h"
dependencies: []
---

# Phase 1: Contracts and registry

## Overview

Author the frozen `contracts.py` (§6.1) and `registry/specs.py` (§3.6) —
the single source of truth every other branch builds against. This is G0.

## Requirements

- Functional: `contracts.py` implements Reading, Assumption, Challenge,
  Approval, ExpectedOutcome, Verification, ToolPermission per §6.1 exactly.
  `registry/specs.py` implements the 9-row device.metric table from §3.6
  (unit, `ttl_batches`, per-scope weight, required flag).
- Non-functional: `wsum(irrigation_plan) == 13`, `wsum(session_check) == 9`,
  `wsum(tank_quality) == 5`.

## Architecture

`registry/specs.py` is the sole source read by: `store/gen_ddl.py` (schema
generation), `trust/` (freshness/weights), `eval/score_scenarios.py`
(segment scoring). No module hand-copies these numbers.

## Related Code Files

- Modify: `contracts.py` (overwrite dev's stub, bump `CONTRACT_VERSION`)
- Create: `registry/specs.py`

## Implementation Steps

1. Fill `contracts.py` dataclasses per §6.1 table.
2. Write `registry/specs.py`: one entry per device.metric row in §3.6,
   with `wsum()` helper per scope.
3. Bump `CONTRACT_VERSION` in `contracts.py` to `"1.0.0"`.
4. PR to `dev`, referencing `plans/260816-0957-farmops-delivery/phase-02-contract-lock.md`.

## Success Criteria

- [ ] `python -c "from registry.specs import wsum; assert wsum('irrigation_plan')==13; assert wsum('session_check')==9; assert wsum('tank_quality')==5"`
- [ ] `contracts.py` has all 7 record types from §6.1 table.
- [ ] `make check-data-plane` passes.

## Risk Assessment

Once merged and frozen this is expensive to change (§7.1 stop-the-line
rule). Mitigate by reviewing against §3.6/§6.1 line by line before opening
the PR, not after.
