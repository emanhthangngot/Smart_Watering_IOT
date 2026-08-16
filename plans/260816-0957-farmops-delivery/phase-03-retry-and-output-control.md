---
phase: 3
title: "Retry and output control"
status: pending
priority: P1
effort: "30m"
dependencies: [1]
---

# Phase 3: Retry and output control

## Overview

One retry ladder and one output-control contract, defined here once and
**referenced, not copied**, by all 5 branch plans.

## Requirements

- Functional: every branch plan's Workspace Rules block points back to this
  file instead of restating the ladder.
- Non-functional: rules are mechanically checkable where possible
  (`scripts/check-ownership.sh`), not honor-system only.

## Architecture — retry ladder

```
Attempt 1  fix in place, rerun the task's verify command
Attempt 2  narrow to the smallest failing unit, rerun
Attempt 3  STOP. Write plans/reports/blocked-{date}-{task-id}.md
           (symptom, exact failing command, shortest decisive error line,
            the 2 attempts made, suspected cause, what you need)
           then notify the integrator on dev.
```

Non-negotiable:
- Never weaken, skip, or `xfail` a test to pass a gate.
- Never insert mock/fake data to satisfy a check. `INCONCLUSIVE` and
  `MISSING` are legal answers; invented numbers are not.
- A failing gate blocks the merge, not the messenger.
- LLM-path retries are already bounded by design (`assert_grounded` 2
  retries → deterministic allocator, `plan.md` §11.1, §7.1). Do not add a
  third retry layer on top.
- Transient Supabase network failure is not a task-level retry — the
  outbox owns it (`plan.md` §11.4).

## Architecture — output control

| Control | Mechanism | Where |
|---|---|---|
| File ownership | `scripts/check-ownership.sh` | `dev`, pre-PR |
| Owner map | `CODEOWNERS` | `dev` |
| Per-task DoD | phase file Success Criteria = runnable command | all branches |
| Contract freeze | `CONTRACT_VERSION` in `contracts.py` | `dev` + M1 |
| Invariant guard | `tests/invariants/test_inv_01..10.py` | owner per invariant |
| Baseline-threshold guard | INV-10: constants checked against §3.1 baselines | M2 |
| Secret guard | `.env.example` only, no key in git/log/frontend | `dev` |
| PR gate | `.github/pull_request_template.md` checklist | `dev` |

## Related Code Files

- Already created: `scripts/check-ownership.sh`, `CODEOWNERS`,
  `.github/pull_request_template.md`
- Referenced by: every `plans/260816-0957-<role>/plan.md` Workspace Rules block

## Implementation Steps

1. This file is the canonical source — done on write.
2. Each branch plan's Workspace Rules block links here instead of restating.

## Success Criteria

- [x] This file exists on `dev`.
- [ ] All 5 branch plans reference it (verified in phase task #3/#4).

## Risk Assessment

Risk: an owner copies the ladder into their own plan and it drifts.
Mitigation: branch plans are instructed to reference this file by path, not
duplicate its content.
