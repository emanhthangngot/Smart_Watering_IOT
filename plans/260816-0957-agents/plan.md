---
status: pending
owner: M3 (feat/agents)
blockedBy: [260816-0957-data-plane, 260816-0957-trust-engine, 260816-0957-tools-runner-api]
blocks: []
---

# M3 — Agents & orchestration

## Workspace rules — read before first commit

```
YOU OWN (create/edit freely):
  worldstate/  agents/  graph/  prompts/  tests/agents/

YOU APPEND ONLY (never reorder, use your own block/section):
  plans/  tests/invariants/test_inv_04.py  docs/agents.md  requirements/agents.txt

YOU READ ONLY (never edit):
  contracts.py  registry/specs.py  trust/  tools/  api/  everything else

NEW top-level directory:      forbidden. Need one? Ask on dev, it gets seeded there.
DELETE / RENAME another's file: forbidden, including "obvious" cleanups.
git add:                      explicit paths only. Never `git add -A` from repo root.
Before every PR:              make check-agents && make ownership && git rebase origin/dev
```

Retry mechanism and output-control contract: see
`plans/260816-0957-farmops-delivery/phase-03-retry-and-output-control.md`
on `dev` — referenced here, not restated.

## Overview

Owns World State, the deterministic agents (Coordinator, Field Evidence,
Diagnosis, Resource), the Planner (deterministic allocator primary, LLM
phrasing only), the Evidence Graph, and active-plan monitoring/replan
(`plan.md` §4.1, §6, §7, §10.2, §11.1). **Last backend layer to merge** —
depends on trust tiers (M2) and the tool layer (M4) both existing first.

## Phases

| # | Title | Depends on |
|---|---|---|
| 01 | World State | G0 (contracts) |
| 02 | Deterministic agents | 01 |
| 03 | Planner | 02, trust tiers (M2) |
| 04 | Grounding and graph | 03 |
| 05 | Monitoring and replan | 04, tool layer (M4) |
| 06 | Reporting | 04 |

## Acceptance

- LLM dead or out of quota → deterministic allocator still produces a plan.
- `assert_grounded` rejects any `evidenceRef` not in `{readingId#metric}`
  from the bundle; 2 retries then falls back to the allocator.
- Every decision traceable via `/explain` back to a real `readingId`.
- One open re-plan per assumption at a time; invalidation key idempotent.
