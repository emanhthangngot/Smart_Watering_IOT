---
status: pending
owner: M1 (feat/data-plane)
blockedBy: []
blocks: [260816-0957-trust-engine, 260816-0957-agents, 260816-0957-tools-runner-api]
---

# M1 — Data plane

## Workspace rules — read before first commit

```
YOU OWN (create/edit freely):
  contracts.py  registry/  ingest/  sim/  store/  eval/  fixtures/  tests/data_plane/

YOU APPEND ONLY (never reorder, use your own block/section):
  plans/  .env.example (# --- M1 feat/data-plane --- block)
  tests/invariants/test_inv_09.py  tests/invariants/test_inv_10.py
  docs/data-plane.md  requirements/data-plane.txt

YOU READ ONLY (never edit):
  everything else — trust/ agents/ graph/ tools/ schedule/ verify/ api/ frontend/

NEW top-level directory:      forbidden. Need one? Ask on dev, it gets seeded there.
DELETE / RENAME another's file: forbidden, including "obvious" cleanups.
git add:                      explicit paths only. Never `git add -A` from repo root.
Before every PR:              make check-data-plane && make ownership && git rebase origin/dev
```

Retry mechanism and output-control contract: see
`plans/260816-0957-farmops-delivery/phase-03-retry-and-output-control.md`
on `dev` — referenced here, not restated.

## Overview

Owns the entire ingestion + storage critical path (`plan.md` §3, §9.2,
§11.4): MQTT client, normalize, registry, Supabase schema + RPC + outbox,
simulator, fixtures, eval harness. **This is the critical path** — G0 and
G1 both belong to this branch and block every other branch.

## Phases

| # | Title | Blocks |
|---|---|---|
| 01 | Contracts and registry | everything (G0) |
| 02 | Supabase schema | everything downstream of storage (G1) |
| 03 | Normalize and outbox | M2 (needs real Reading stream) |
| 04 | MQTT client | phase 03 |
| 05 | Simulator | M2 water-balance testing |
| 06 | Fixtures and eval | M2 (F1-F4 test contract), INV-9 |

## Acceptance

- `wsum` assertions pass (13/9/5).
- One real batch writes 6 Supabase tables, reads back via `readings_all`.
- Unknown metric / non-finite value / missing time fields → counters, no crash.
- `eval/score_scenarios.py` imports nothing from `trust/` or `agents/` (INV-9).
- F1-F4 fixtures committed and used by M2 as its own test contract.
