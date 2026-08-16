---
phase: 4
title: "API and auth"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 4: API and auth

## Overview

Endpoints per §11.3, each as its own `api/routers/*.py` module
(auto-discovered by dev's `api/main.py`); `X-Operator-Token` on all writes;
`actor` derived from token, never request body (§7.4).

## Requirements

- Functional: endpoints — `POST /farm/request`, `GET /farm/state`,
  `GET /farm/plan/{revisionId}`, `GET /trust/current`,
  `GET /explain/{decisionId}`, `GET /timeline/{traceId}`,
  `POST /approvals/{planRevisionId}/approve|reject`, `GET /tasks`,
  `POST /tasks/{id}/acknowledge|resolve`, `POST /sim/...` (only when
  `ACTUATION_TARGET=sim`), `GET /health`.
- Non-functional: token id (not the token) logged in audit rows.
  `expiresAt` default 30 min on approvals; expired approval → plan
  `EXPIRED`, never auto-runs.

## Architecture

Each router file owns one resource group, exports `router = APIRouter()`.
dev's `api/main.py` includes it automatically — never add a router to a
shared list by hand.

## Related Code Files

- Create: `api/deps.py` (operator-token dependency), `api/auth.py`,
  `api/routers/farm.py`, `api/routers/trust.py`, `api/routers/explain.py`,
  `api/routers/timeline.py`, `api/routers/approvals.py`,
  `api/routers/tasks.py`, `api/routers/sim.py`, `api/routers/health.py`

## Implementation Steps

1. `api/auth.py`: validate `X-Operator-Token` against env, resolve `actor`
   from the token — never from request body.
2. `api/deps.py`: FastAPI dependency wrapping auth for reuse across routers.
3. One router file per resource group, each a thin layer over `agents/`,
   `graph/`, `tools/`, `verify/` (M3/M4 modules) — no business logic here.
4. `api/routers/sim.py`: only mounts/responds when `config.actuation_target
   == "sim"`.

## Success Criteria

- [ ] Every write endpoint (`/approvals/*`, `/farm/request`, `/sim/*`) 401s without a valid `X-Operator-Token`.
- [ ] Audit row `actor` field matches the token's resolved identity, never a client-supplied value.
- [ ] `/sim/*` returns 404/disabled when `ACTUATION_TARGET != "sim"`.
- [ ] `tests/invariants/test_inv_08.py` (no path touches real hardware under any `ACTUATION_TARGET`) passes.

## Risk Assessment

§7.4's whole point: an anonymous or self-declared `actor` makes the audit
trail worthless. Verify by testing that a forged body `actor` field is
silently ignored, not merely "usually" ignored.
