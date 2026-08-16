---
status: pending
owner: M4 (feat/tools-runner-api)
blockedBy: [260816-0957-data-plane, 260816-0957-trust-engine]
blocks: [260816-0957-agents]
---

# M4 — Tools, runner, API

## Workspace rules — read before first commit

```
YOU OWN (create/edit freely):
  tools/  schedule/  verify/  api/  tests/tools/

YOU APPEND ONLY (never reorder, use your own block/section):
  plans/  .env.example (# --- M4 feat/tools-runner-api --- block)
  tests/invariants/test_inv_01.py test_inv_02.py test_inv_03.py
    test_inv_05.py test_inv_06.py test_inv_08.py
  docs/api.md  requirements/tools-runner-api.txt

YOU READ ONLY (never edit):
  contracts.py  registry/specs.py  trust/  agents/  everything else

NEW top-level directory:      forbidden. Need one? Ask on dev, it gets seeded there.
DELETE / RENAME another's file: forbidden, including "obvious" cleanups.
git add:                      explicit paths only. Never `git add -A` from repo root.
Before every PR:              make check-tools && make ownership && git rebase origin/dev
```

Retry mechanism and output-control contract: see
`plans/260816-0957-farmops-delivery/phase-03-retry-and-output-control.md`
on `dev` — referenced here, not restated.

## Overview

Owns the only layer allowed to cause a side effect: tool permission
checks, schedule runner, two-layer verification, the FastAPI app + auth,
restart recovery, retention, water ledger (`plan.md` §7.3, §9, §10.1,
§10.4, §11.3, §8). Endpoints live as auto-discovered `api/routers/*.py`
modules (dev's `api/main.py` already wires discovery — see
`plans/260816-0957-farmops-delivery/phase-01-skeleton-and-config.md`).

## Phases

| # | Title | Invariants |
|---|---|---|
| 01 | Tool layer | INV-6 |
| 02 | Schedule runner | INV-1, INV-2, INV-3 |
| 03 | Verification | — |
| 04 | API and auth | — |
| 05 | Recovery and retention | — |
| 06 | Water ledger | INV-2 |

## Acceptance

- No side-effect tool call happens without plan status + tier + approval +
  revision hash + idempotency check passing first (INV-6).
- Never two `RUNNING` schedules on one pump (INV-3, DB-enforced).
- `INCONCLUSIVE` never reported as `PASS`.
- No actuation path touches real hardware under any `ACTUATION_TARGET`
  value (INV-8).
