/mo---
status: pending
owner: M2 (feat/trust-engine)
blockedBy: [260816-0957-data-plane]
blocks: [260816-0957-agents, 260816-0957-tools-runner-api]
---

# M2 — Trust engine

## Workspace rules — read before first commit

```
YOU OWN (create/edit freely):
  trust/  tests/trust/

YOU APPEND ONLY (never reorder, use your own block/section):
  plans/  tests/invariants/test_inv_07.py  docs/trust.md  requirements/trust-engine.txt

YOU READ ONLY (never edit):
  contracts.py  registry/specs.py  fixtures/  everything else

NEW top-level directory:      forbidden. Need one? Ask on dev, it gets seeded there.
DELETE / RENAME another's file: forbidden, including "obvious" cleanups.
git add:                      explicit paths only. Never `git add -A` from repo root.
Before every PR:              make check-trust && make ownership && git rebase origin/dev
```

Retry mechanism and output-control contract: see
`plans/260816-0957-farmops-delivery/phase-03-retry-and-output-control.md`
on `dev` — referenced here, not restated.

## Overview

Owns freshness/trust scoring (`plan.md` §4): reading states, hard-fail vs
soft-penalty rules, DCS formula, tier with hysteresis, water-balance
physics, expected-vs-actual predicates. **Blocked by G0** (contracts +
registry + F1-F4 fixtures from `feat/data-plane`) — do not start phase 03
(DCS) before those merge to `dev`.

## Phases

| # | Title | Gate |
|---|---|---|
| 01 | Freshness and states | — |
| 02 | Hard-fail / soft-penalty rules | — |
| 03 | DCS and tier | G2 (4 fixtures → 4 tiers) |
| 04 | Water-balance | — |
| 05 | Expected-vs-actual | — |

## Acceptance

- F1 → AUTO, F2 → PROPOSE, F3 → INVESTIGATE, F4 → INVESTIGATE (`test_trust.py`).
- Every rule is a pure `(bundle, windows) -> bool`, never raises.
- `stuck_at` requires bit-identical value **and** a correlated in-scope
  signal that moved — never fires on legitimately-stable low-res sensors.
- pH stays advisory in `tank_quality` only, never blocks `irrigation_plan`.
