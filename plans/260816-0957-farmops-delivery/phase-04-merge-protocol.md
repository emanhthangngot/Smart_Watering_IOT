---
phase: 4
title: "Merge protocol"
status: pending
priority: P1
effort: "n/a — process document"
dependencies: [1, 2]
---

# Phase 4: Merge protocol

## Overview

The master merge plan: order, hygiene rules, and conflict adjudication for
landing all 5 branches into `dev` without silent drift.

## Requirements

- Functional: every merge into `dev` is preceded by its required gate
  passing (see table below).
- Non-functional: `dev` stays green — `make check` passes after every merge,
  or the merge is reverted, not patched around.

## Architecture

### Branch hygiene

- Rebase, never merge backwards: `git fetch origin && git rebase origin/dev`
  before every PR. `dev` is never merged *into* a feature branch.
- Squash-merge into `dev`, one commit per phase, conventional format,
  scoped (`feat(trust): ...`), no AI references.
- PR is per phase, not per branch — a 4000-line PR will not be reviewed.
- Rebase conflicts inside your own owned paths: you fix them. Conflicts
  outside your owned paths: stop, it means the ownership rule broke
  somewhere — the integrator on `dev` adjudicates.

### Merge order

| # | Merge | Gate required | Why this order |
|---|---|---|---|
| 1 | `feat/data-plane` phase-01 → `dev` | G0 contract frozen | unblocks the other 4 branches |
| 2 | `feat/data-plane` phase-02 → `dev` | G1 batch written + read via `readings_all` | every consumer needs a real read path |
| 3 | `feat/data-plane` phases 03-06 → `dev` | fixtures F1-F4 committed | M2's test contract must exist first |
| 4 | `feat/trust-engine` → `dev` | G2 four fixtures → four tiers | M3/M4 consume tier decisions |
| 5 | `feat/tools-runner-api` → `dev` | INV-1/2/3/6/8 pass | agents need the tool layer + API to act through |
| 6 | `feat/agents` → `dev` | INV-4 no dangling edges | last backend layer, depends on trust + tools |
| 7 | `feat/operator-ux` → `dev` | 390px screens intact | no backend file overlap — may merge any time after G1 |

### Conflict adjudication

| Conflict class | Resolution |
|---|---|
| Frozen contract field | Stop the line. Announce, bump `CONTRACT_VERSION`, everyone rebases. Never resolve silently. |
| Generated file (`store/schema.sql`) | Discard both sides, rerun `store/gen_ddl.py`, commit regenerated output |
| `requirements/<role>.txt` | Cannot conflict by construction; if it does, someone edited another owner's file |
| Append-only file (`.env.example`, `tests/invariants/`) | Keep both blocks, preserve owner tags, never reorder |
| Anything outside your owned paths | Ownership violation — revert your side, redo through the owner |

## Related Code Files

- Read: `CODEOWNERS`, `scripts/check-ownership.sh`
- No new files — this phase is process, applied at merge time.

## Implementation Steps

1. Integrator runs `scripts/check-ownership.sh` on every incoming PR before merge.
2. Integrator confirms the required gate (see table) actually ran and passed.
3. Squash-merge, tag the commit with the phase it closes.
4. Run `make check && make ownership && make invariants` on `dev` HEAD.
5. If red: revert the merge, do not patch on top.

## Success Criteria

- [ ] Every merge to `dev` is traceable to a passed gate (commit message or PR link).
- [ ] `dev` never sits red for more than one merge cycle.

## Risk Assessment

Risk: pressure to merge out of order under time pressure. Mitigation: the
order exists because of real dependency chains (M2/M3/M4 need M1's contract
and fixtures; M3 needs M4's tool layer) — merging early just moves the
failure later and makes it harder to attribute.
