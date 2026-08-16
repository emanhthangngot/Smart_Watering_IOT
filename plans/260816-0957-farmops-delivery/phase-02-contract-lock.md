---
phase: 2
title: "Contract lock (G0)"
status: pending
priority: P1
effort: "2h"
dependencies: [1]
---

# Phase 2: Contract lock (G0)

## Overview

`contracts.py` and `registry/specs.py` plus the F1–F4 fixtures are the
single frozen contract everyone else builds against (`plan.md` §6.1, §3.6,
§4.4). Owned and authored by `feat/data-plane`, merged to `dev`, then
frozen. This is the highest-leverage gate: nothing else may safely merge
before it.

## Requirements

- Functional: `contracts.py` fields match §6.1 exactly (Reading,
  Assumption, Challenge, Approval, ExpectedOutcome, Verification,
  ToolPermission). `registry/specs.py` matches the §3.6 table exactly —
  unit, `ttl_batches`, scope weights, required flags for all 9
  device.metric rows.
- Non-functional: `wsum(irrigation_plan) == 13`, `wsum(session_check) == 9`,
  `wsum(tank_quality) == 5` as asserted constants, not magic numbers
  recomputed elsewhere.

## Architecture

Once merged and tagged frozen, `CONTRACT_VERSION` in `contracts.py` is the
authority. Any change to a frozen field requires bumping this constant and
an announcement on `dev` — never a silent edit (`plan.md` §7.1 "critical
path is M1... Đổi contract sau khi khoá thì dừng lại và thông báo cả nhóm").

## Related Code Files

- Modify: `contracts.py` (dev's stub → frozen version)
- Create: `registry/specs.py`
- Create: `fixtures/f1_bundle_healthy.json`, `fixtures/f2_bundle_stale.json`,
  `fixtures/f3_bundle_broken.json`, `fixtures/f4_bundle_stuck.json`
  (numbers from `plan.md` §4.4)

## Implementation Steps

1. `feat/data-plane` authors `contracts.py` fields + `registry/specs.py`.
2. Author F1–F4 fixtures with the exact hand-computed values from §4.4.
3. PR to `dev`, ownership check passes, `wsum` assertions pass.
4. On merge: tag `CONTRACT_VERSION = "1.0.0"`, announce freeze on `dev`.

## Success Criteria

- [ ] `python -c "from registry.specs import wsum; assert wsum('irrigation_plan')==13"`
- [ ] 4 fixture files exist and parse as valid JSON matching the FARM payload shape.
- [ ] `CONTRACT_VERSION` bumped from `"0.0.0-unfrozen"`.

## Risk Assessment

Frozen-too-early risk: if the real MQTT payload later disagrees, this gate
is exactly where the mismatch surfaces first — before 4 other branches
build on a wrong assumption. Mitigation: `plan.md` §16 already tracks this
("Payload thật khác input_format.txt").
