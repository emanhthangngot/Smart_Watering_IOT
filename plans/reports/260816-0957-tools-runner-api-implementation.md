# M4 tools-runner-api — implementation report

Date: 2026-08-16
Branch: `feat/tools-runner-api`
Design source: `plans/reports/plan.md` v5.2
Task source: `plans/260816-0957-tools-runner-api/`

## Delivered

- Permission-gated irrigation tool layer with approval/revision/evidence/tier
  checks resolved from an authoritative state port, grounded-evidence and
  parameter validation, canonical idempotency keys, duplicate replay,
  ambiguous-failure hold, complete inspection-task fallback parameters, and a
  maximum two-hop safety downgrade. Persisted schedules are re-authorized
  against current approval/revision/evidence immediately before every run.
- Five-second schedule runner contract with atomic claims, no catch-up after the
  two-minute grace window, fail-closed tank checks, one-running-pump enforcement,
  cancellation on invalidated plan states, non-finite telemetry rejection,
  bounded verification recovery, mandatory water-budget/ledger boundaries,
  and `none|sim`-only actuation.
- Separate action and outcome verification; observational `none` mode preserves
  `INCONCLUSIVE` and never treats it as `PASS`.
- Water-ledger reconciliation and active daily drawdown budget query.
- Startup recovery ports for missed/running schedules, executing plans, expired
  approvals, missing verifications, and the INV-5 two-window terminal deadline.
- Rollup-first, 5,000-row bounded retention orchestration behind an M1 port.
- Auto-discovered FastAPI routers, write authentication, credential-derived
  actor/token id audit data, exact revision-hash approval, 30-minute approval
  expiry, dependency-aware health, and fail-closed simulator routing.
- FastAPI lifespan orchestration: recovery-before-runner, continuous expiry,
  hourly retention scheduling, guarded background-task restart, and clean
  shutdown. Missing M1 integrations are reported as `BLOCKED_M1`.
- `/sim` is restricted to idempotent fault controls; public pump start/stop can
  no longer bypass the irrigation permission layer.
- API documentation and operator environment example.

## Verification

Executed with the bundled Python runtime because the host Python installation
does not include `venv`/the project dependencies.

```text
ruff check tools schedule verify api tests/tools <owned invariant files>
All checks passed!

pytest -q tests/tools tests/invariants -m 'tools or invariants'
70 passed in 1.08s

mypy tools schedule verify api
Success: no issues found in 32 source files
```

The suite includes an approved tool → action read-back → schedule runner →
observational outcome → water-ledger integration flow and regression tests for
NaN tank data, verification outages, idempotency collisions, simulator bypass,
runtime startup ordering, and continuous expiry.

## Integration blockers (not bypassed)

M4 core behavior and local adapters are complete, but the branch is not a
production-complete vertical slice until its declared dependencies merge:

1. G0 is open: `contracts.py` remains `0.0.0-unfrozen`.
2. M1 storage is absent: `store/db.py` and `store/schema.sql` do not exist.
   Therefore the Postgres transactional claim, persistent idempotency store,
   retention transaction, water-ledger persistence, and the required partial
   unique index on a RUNNING pump cannot yet be integration-tested.
3. M2 expected-outcome evaluator is absent: `trust/expected.py` does not exist.
   Outcome verification currently consumes a typed result at its port boundary.
4. M3 agents are not connected. API read endpoints expose `PARTIAL` or
   `UNAVAILABLE` instead of inventing telemetry, trust, plans, or explanations.
5. No causal simulator adapter is present. `ACTUATION_TARGET=sim` returns `503`
   until one is connected; all other/unknown targets remain non-actuating.

No files in M1, M2, M3, M5, `contracts.py`, or `registry/specs.py` were edited.
