---
status: pending
owner: M5 (feat/operator-ux)
blockedBy: []
blocks: []
---

# M5 — Frontend & operator UX

## Workspace rules — read before first commit

```
YOU OWN (create/edit freely):
  frontend/   (nothing else, ever)

YOU APPEND ONLY (never reorder, use your own block/section):
  plans/  docs/frontend.md

YOU READ ONLY (never edit):
  everything backend — contracts.py, registry/, ingest/, sim/, store/,
  eval/, fixtures/, trust/, worldstate/, agents/, graph/, prompts/,
  tools/, schedule/, verify/, api/, requirements/*.txt (except your own)

NEW top-level directory:      forbidden outside frontend/. Need one at repo
                               root? Ask on dev, it gets seeded there.
DELETE / RENAME another's file: forbidden, including "obvious" cleanups.
git add:                      explicit paths only. Never `git add -A` from repo root.
Before every PR:              make check-frontend && make ownership && git rebase origin/dev
```

Retry mechanism and output-control contract: see
`plans/260816-0957-farmops-delivery/phase-03-retry-and-output-control.md`
on `dev` — referenced here, not restated.

## Overview

Owns the operator UI (`plan.md` §11.2): Farm State, Plan Detail, Approval,
Inspection Tasks, Trace, health panel — all responsive down to 390px.
**Not blocked by anything on the critical path** — `frontend/` shares no
file with the backend, so it can merge as soon as it is green, any time
after G1 (a real API to talk to). No copied code from
`origin/feat/mqtt-telemetry-viewer` — architecture pattern only (app-router
layout, `design-system/` markdown contract, Tailwind 4, React 19), rebuilt
fresh against our own FastAPI.

## Phases

| # | Title |
|---|---|
| 01 | Architecture (fresh scaffold) |
| 02 | Farm State and health panel |
| 03 | Plan and approval |
| 04 | Verification and tasks |
| 05 | Trace and responsive |

## Acceptance

- No file under `frontend/` copied verbatim from another repo — architecture
  pattern reused, code written fresh.
- No drizzle/Cloudflare-worker/D1 dependency carried over — talks only to
  our FastAPI.
- Every screen intact at 390px width.
- Freshness/tier always shown with a reason in words, not color alone.
