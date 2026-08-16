---
status: in-progress
owner: dev (integrator)
blockedBy: []
blocks: []
---

# FarmOps AI — delivery coordination (dev)

## Overview

`dev` is the integration branch for the 5-person build of FarmOps AI
(design: `plans/reports/plan.md` v5.2). This folder does not implement
FarmOps — it owns the skeleton, the merge protocol, the retry/output-control
contract every branch references, and the integration gates. Full design
rationale lives in `plans/reports/plan.md`; this folder only adds the
executable team layer on top of it.

## Branch map

```
main
 └─ dev
     ├─ feat/data-plane        M1
     ├─ feat/trust-engine      M2
     ├─ feat/agents            M3
     ├─ feat/tools-runner-api  M4
     └─ feat/operator-ux       M5
```

All 5 branch from `dev`, never from each other. PRs target `dev`.
`dev → main` only at gate G5.

## Owner table

| Role | Branch | Owns | Append-only | Read-only |
|---|---|---|---|---|
| M1 | `feat/data-plane` | `contracts.py`, `registry/`, `ingest/`, `sim/`, `store/`, `eval/`, `fixtures/`, `tests/data_plane/` | `plans/`, `.env.example`, `tests/invariants/`, `docs/`, `requirements/` | everything else |
| M2 | `feat/trust-engine` | `trust/`, `tests/trust/` | same as above | everything else |
| M3 | `feat/agents` | `worldstate/`, `agents/`, `graph/`, `prompts/`, `tests/agents/` | same as above | everything else |
| M4 | `feat/tools-runner-api` | `tools/`, `schedule/`, `verify/`, `api/`, `tests/tools/` | same as above | everything else |
| M5 | `feat/operator-ux` | `frontend/` | `plans/`, `docs/` | everything else |

`worldstate/` is an addition to `plan.md` §13.3 — the design names World
State (§4.1) but assigns no directory. Assigned to M3 here; this table is
the single answer, cross-referenced from `CODEOWNERS`.

## Critical path

M1 (`feat/data-plane`) is the critical path. `contracts.py` + `registry/specs.py`
+ fixtures F1–F4 must land and freeze (G0) before anything else can safely
build. `store/schema.sql` applied and read back through `readings_all` (G1)
blocks every data consumer. See `plan.md` §13.2 for the full vertical order.

## Cut list (from `plan.md` §13.3, in order)

P2 → Ghost Farm → Agent Constellation → Reporting (merge the two personas) →
rule K from 5 down to 2 (`pump_on_soil_flat`, `tank_drain_no_pump`) →
`PH_01`/`SUN_01` out of DCS (still displayed, still 4/6 device minimum).

**Never cut:** trust engine hard-fail/cap, tier enforcement at the tool
layer, schedule runner, the two verification layers, `/explain`, restart
recovery.

## Phases in this folder

| Phase | Title | Status |
|---|---|---|
| 01 | Skeleton and config | completed (this session) |
| 02 | Contract lock (G0) | pending — owned by `feat/data-plane` |
| 03 | Retry and output control | pending |
| 04 | Merge protocol | pending |
| 05 | Integration gates | pending |

## Acceptance

- `dev` skeleton seeded, `make check` passes on empty skeleton.
- 5 branches exist off `dev`, each with exactly one plan folder.
- `scripts/check-ownership.sh` rejects cross-owner writes and new top-level dirs.
- G0–G5 defined with an executable command per gate.
