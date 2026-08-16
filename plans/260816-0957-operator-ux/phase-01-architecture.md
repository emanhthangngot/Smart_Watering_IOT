---
phase: 1
title: "Architecture (fresh scaffold)"
status: pending
priority: P1
effort: "2h"
dependencies: []
---

# Phase 1: Architecture (fresh scaffold)

## Overview

Fresh frontend scaffold reproducing the architecture pattern seen on
`origin/feat/mqtt-telemetry-viewer` — app-router structure, a
`design-system/` markdown contract, Tailwind 4, React 19 — with **no
copied code** and no Cloudflare/drizzle/worker baggage. Talks only to our
own FastAPI (M4).

## Requirements

- Functional: `frontend/` is self-contained with its own `package.json`,
  no shared dependency file with the backend.
- Non-functional: no `drizzle-orm`, `wrangler`, `@cloudflare/*`, or `worker/`
  directory — those were specific to the prior repo's Cloudflare Workers
  target, not needed here.

## Architecture

Pattern reused (not code): `app/` router-style pages, a `design-system/`
folder holding a short markdown spec (tokens, component conventions) that
later phases follow, Tailwind 4 for styling, React 19. API calls go through
a single typed client module pointing at the FastAPI base URL from env.

## Related Code Files

- Create: `frontend/package.json`, `frontend/app/`, `frontend/design-system/MASTER.md`,
  `frontend/.gitignore`, `frontend/api-client.ts` (or equivalent typed client)

## Implementation Steps

1. Scaffold a minimal React 19 + Tailwind 4 app under `frontend/` (Vite or
   equivalent — no Cloudflare-specific tooling).
2. Write `frontend/design-system/MASTER.md`: tokens (color, spacing, type)
   and component conventions, written fresh for this project.
3. Write a typed API client hitting the FastAPI base URL (from an env var,
   not hard-coded).
4. `frontend/.gitignore`: `node_modules/`, build output.

## Success Criteria

- [ ] `frontend/package.json` has no `drizzle-orm`, `wrangler`, or `@cloudflare/*` dependency.
- [ ] `grep -r` across `frontend/` for any string copied verbatim from the reference branch returns nothing (spot-check a few distinctive lines).
- [ ] `npm run build` (or equivalent) succeeds from a clean `frontend/`.

## Risk Assessment

Temptation to `git show origin/feat/mqtt-telemetry-viewer:frontend/... > file`
directly — explicitly against the user's instruction (architecture only,
no code copy). Write every file fresh even where the shape rhymes.
