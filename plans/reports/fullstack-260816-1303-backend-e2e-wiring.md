# Backend E2E Wiring Report

## Task
Wire the real sim -> ingest -> trust -> agents -> tools -> schedule -> verify
pipeline end-to-end, replacing `api/service.py`'s stub, using only the
sanctioned local-dev path (`ACTUATION_TARGET=sim`, no MQTT credentials).

## What was wired

1. **Sim ingest loop** (`api/pipeline.py::FarmPipeline.tick`) — ticks a live
   `sim.world.WorldState` every 5s, publishes a batch via
   `sim.publisher.build_batch` (identical shape to the real broker), writes it
   through `store.ingest.ingest_raw_batch` (same call path as
   `store/smoke_test.py`), and updates in-memory read caches
   (latest value per device.metric, a rolling window per key for the
   trust engine's `stuck_at`/delta rules, reading rows for the evidence graph).
2. **Trust engine** — after each tick, `FarmPipeline._recompute_trust` calls
   `trust.score.score_scope` for all three `registry.specs.SCOPES` and for a
   synthetic per-device scope (weight=1, required=True over that device's own
   metrics), then `trust.tier.evaluate_tier` for hysteresis. Feeds
   `GET /trust/current`, `GET /farm/state` device tiers/DCS/reasons, and
   `GET /health`.
3. **Real health** (`FarmPipeline.health_snapshot`) — `batchPeriodSeconds`
   from `ingest.cadence.CadenceTracker`, `lateRatio`/`clockSkewSeconds` from
   real counters/`ClockTracker`, `outboxDepth` from
   `store.outbox_drain.outbox_depth()`.
4. **Real farm state** (`FarmPipeline.devices_snapshot`/`evidence_health`) —
   per-device freshness via `trust.states.assign_state`, DCS/tier/reasons via
   the per-device trust score, `evidenceHealth` computed from
   `registry.required_specs("irrigation_plan")` vs. actual freshness.
5. **Planner -> PlanRevision** (`api/workflow.py::SimFarmWorkflow.submit_request`,
   wired via `service.configure_workflow`) — builds a real
   `agents.allocator.AllocationRequest` from the live `WorldState` (tank
   level, soil moisture), calls `agents.planner.plan(..., narrator=None)`
   (LLM boundary stays disabled — no API key required, matches
   `config.llm_enabled` fail-closed default), and turns the deterministic
   `AllocationResult` into a real `contracts.PlanRevision` + hash
   (`contracts.compute_revision_hash`). Persisted both in `service.plans`
   (source of truth for the API) and durably in Postgres via
   `store.db.append_plan_revision` (best-effort — logged, not fatal, if the
   DB write fails; the in-memory plan stays authoritative for that run).
6. **Approval -> execution** (`SimFarmWorkflow.on_approved`, hooked from
   `service.decide_approval` on `APPROVE`) — builds a real
   `tools.permission.ToolContext`/`contracts.Approval`, calls
   `tools.irrigation.IrrigationToolLayer.execute("create_irrigation_schedule", ...)`.
   The tool layer's own safety-downgrade ladder (`tools/downgrade.py`) is
   respected: if the plan's live trust tier is below `PROPOSE`, the request
   downgrades to `create_inspection_task` and the plan is marked
   `NEEDS_REPLAN` instead of falsely staying `EXECUTING`. A real
   `verify.action.verify_action` runs immediately (post-result + read-back
   from the schedule repository) and is recorded on the plan.
7. **Schedule runner -> sim actuator** — `schedule.runner.ScheduleRunner`
   (real, unmodified) is started as a background task via
   `api/runtime.py`'s existing `RuntimeCoordinator`. Its `SimulatorActuation`
   callback flips `FarmPipeline.set_pump()`, which is read by the next
   `sim.world.WorldState.tick()` call — the actual `ACTUATION_TARGET=sim`
   closed loop described in `sim/publisher.py`'s docstring: approving a plan
   really turns the pump on in the shared world state, and the next
   published batch shows the causal soil/tank effect.
8. **Outcome verification** — on schedule close, `verify.outcome.verify_outcome`
   evaluates the plan's `ExpectedOutcome` (SOIL_01 soil-moisture rise) against
   the real ingested trajectory via `trust.expected.evaluate`, recorded as an
   `OUTCOME` `Verification` on the plan; `verify.ledger.InMemoryWaterLedger`
   records the schedule outcome.
9. **Inspection tasks from real trust findings** — `FarmPipeline._raise_findings`
   diffs each device's `rules_fired` tick over tick; `api/wiring.py::_on_trust_finding`
   creates a real `service.tasks` entry (deduped per open task) when a hard
   trust rule (e.g. `stuck_at`, `source_not_ok`) fires for a device — not
   hardcoded content.
10. **Explain / graph** — `graph.edges.EvidenceGraph` + `graph.explain.trace_to_readings`
    (both frozen, unmodified) are populated with real `reading -> decision`
    edges when a plan is proposed; `GET /explain/{decisionId}` traces them
    back to the actual ingested reading rows.
11. **Timeline** — every step above appends a real event to
    `service.timeline[traceId]` (`FARM_REQUESTED` -> `PLAN_PROPOSED` ->
    `FARM_REQUEST_ACCEPTED` -> `ACTION_EXECUTED` -> `PLAN_EXECUTING` ->
    `ACTUATOR_START`/`STOP` -> `OUTCOME_VERIFIED`).
12. **`/sim/*` fault injection** — `api/wiring.py::_SimAdminAdapter` now
    operates on the *same* live `sim.faults.FaultFlags`/`sim.world.WorldState`
    the ingest loop reads, so `inject-fault sensor_stuck` genuinely freezes
    the next published batch.

## Files touched

- `api/pipeline.py` (new, 398 lines) — sim/ingest/trust data plane.
- `api/workflow.py` (new, 649 lines) — planner, approval execution, schedule
  runner wiring, outcome verification, DB persistence of plan revisions.
- `api/wiring.py` (new, 176 lines) — process-startup construction, fault
  adapter, trust-finding -> inspection-task glue, ingest-loop task
  lifecycle.
- `api/e2e_smoke.py` (new, 188 lines) — HTTP-only proof script.
- `api/service.py` (edited) — added `TelemetryPort`, `configure_telemetry`,
  real `farm_state()`/`health()`, `upsert_plan`/`set_plan_status`/
  `record_verification`/`append_timeline_event`/`record_explanation`/
  `add_task`/`scope_verdicts`, and hooked `decide_approval` to call
  `workflow.on_approved` on `APPROVE`. Public method signatures used by
  routers are unchanged.
- `api/main.py` (edited) — lifespan now calls `wiring.build()`/`wiring.start()`/
  `wiring.stop()` around the existing `runtime.start()`/`stop()`.
- `api/routers/trust.py` (edited) — `GET /trust/current` returns real
  `service.scope_verdicts()` instead of a hardcoded `UNAVAILABLE` stub.

No file outside `api/` was modified. `contracts.py`, `registry/`, `ingest/`,
`sim/`, `store/`, `trust/`, `worldstate/`, `agents/`, `graph/`, `prompts/`,
`tools/`, `schedule/`, `verify/` are all untouched — every wire above calls
into the existing frozen public API of those modules.

## Test results

```
.venv/bin/pytest -q tests/tools tests/agents tests/trust tests/data_plane tests/invariants
229 passed, 1 warning in 0.91s
```

Full repo suite (`.venv/bin/pytest -q`, same 229 — no other test directories
are collected) also passes. One pre-existing assertion
(`tests/tools/test_runtime.py::test_fastapi_lifespan_starts_expiry_and_reports_missing_integrations`)
expected `recovery == "BLOCKED_M1"`; this is preserved as-is (see "Deliberately
left unwired" below) rather than weakened.

```
ruff check api
All checks passed!
```

## E2E smoke script output

Run against a live `uvicorn api.main:app` with local Postgres up
(`docker compose -f store/docker-compose.yml up -d --wait`):

```
$ OPERATOR_TOKEN=dev-local-token ACTUATION_TARGET=sim \
    .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 &
$ OPERATOR_TOKEN=dev-local-token .venv/bin/python -m api.e2e_smoke

PASS — health reports a real batch period (data plane is live)
PASS — POST /farm/request creates a real plan revision
PASS — GET /farm/plan/PLAN-CF2DAD2B-V1 returns PROPOSED with actions
PASS — POST /approvals/PLAN-CF2DAD2B-V1/approve executes the plan
PASS — schedule runner drives the plan to a terminal status with real verifications
PASS — GET /timeline/trace_b26879ea25 shows the full PROPOSED->APPROVED->EXECUTING sequence
PASS — GET /explain/decision_PLAN-CF2DAD2B-V1 returns real evidence nodes
PASS — GET /tasks returns the inspection task list

e2e_smoke: OK — plan PLAN-CF2DAD2B-V1 reached DONE
```

Verified manually via `curl` too (captured during development): the plan's
`verifications` array held both an `ACTION` `PASS` (post-result + read-back
matched) and an `OUTCOME` `PASS` (real soil-moisture rise of ~0.19-0.8%
observed over the schedule window, evaluated by `trust.expected.evaluate`
against the actual ingested trajectory) once the pump genuinely ran in the
sim world.

Note: `PLAN_DURATION_MINUTES`/`PLAN_WINDOW_MINUTES` in `api/workflow.py` are
set to 1 / 5 minutes (not a farm-realistic 10+/30) specifically so the
approve -> execute -> outcome-verify loop closes within a demo/smoke-test
horizon; the mechanism is unchanged either way, only the numbers.

## Deliberately left unwired / narrowed scope

- **Startup recovery (`api/recovery.py`) and retention (`api/retention.py`)**
  are not wired (`runtime.configure(startup_recovery=None, retention_job=None, ...)`,
  reported as `BLOCKED_M1` on `/health`'s `runtime` block, matching the
  pre-existing `tests/tools/test_runtime.py` assertion). Both need durable
  storage for approvals/actions/schedules (recovery) and the sensor-reading
  tables (retention) that this pass keeps in-memory in `service.py`'s
  existing façade for everything except plan revisions/edges. Wiring a no-op
  there would have misreported "READY" for an integration that is not
  actually restart-safe — narrowed honestly rather than faked.
- **Full Postgres persistence of approvals/verifications/tasks/schedules**:
  only `plan_revisions` + `edges` are durably written (via
  `store.db.append_plan_revision`, best-effort, non-fatal on failure).
  Approvals, verifications, inspection tasks and schedules stay in
  `service.py`'s in-memory dicts / `InMemoryScheduleRepository` /
  `InMemoryWaterLedger` / `InMemoryToolStateStore` — the same adapters
  `tests/tools/test_end_to_end_flow.py` already exercises. `store/schema.sql`
  has tables for all of these; adding real repositories for each was out of
  budget for this pass and is the natural next increment.
- **Trust-engine artifact worth noting, not a bug**: `sim/world.py` never
  varies `WEATHER_01`, `SUN_01`, or `PH_01` over time (no environmental
  model), and `TANK_01.level` is exactly constant whenever the pump is idle
  (no leak fault active). Given enough idle ticks, `trust.rules.stuck_at`
  (frozen, unmodified) legitimately fires for those devices/metrics — this
  is real detection of genuinely static telemetry, not a wiring defect, but
  it means a long-running dev server will accumulate `stuck_at` findings
  and inspection tasks for those three devices, and `irrigation_plan`
  DCS/tier can decay into `INVESTIGATE` over time, triggering the tool
  layer's safety downgrade (schedule -> inspection task) on later requests.
  `SimFarmWorkflow.on_approved` now correctly reflects this as
  `NEEDS_REPLAN` (not a false `EXECUTING`) when it happens.

## How to run the full stack locally

```bash
# 1. Local Postgres (schema auto-applied via docker-entrypoint-initdb.d)
docker compose -f store/docker-compose.yml up -d --wait

# 2. API + sim ingest loop + schedule runner, in one process
OPERATOR_TOKEN=dev-local-token ACTUATION_TARGET=sim \
  .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

# 3. Proof script (separate terminal; does not start/stop the server)
OPERATOR_TOKEN=dev-local-token .venv/bin/python -m api.e2e_smoke
```

No `MQTT_*`/`SUPABASE_*` env vars are required — `store/db.py` falls back to
the local Docker Postgres automatically, and `ACTUATION_TARGET=sim` selects
the in-process `sim.publisher`/`sim.world` feed instead of
`ingest/mqtt_client.py`.

## Unresolved questions

None blocking. Two follow-ups worth a future phase: (1) durable
`RecoveryPort`/`RetentionPort` implementations once approvals/actions get
their own Postgres repositories; (2) whether `sim/world.py` should get a
tiny periodic jitter for WEATHER_01/SUN_01/PH_01 so `stuck_at` does not
chronically fire on a long-running demo — that's a `sim/` (frozen) change
outside this phase's file ownership, flagged rather than patched.

Status: DONE
Summary: Wired the real sim -> ingest -> trust -> agents -> tools -> schedule -> verify -> API pipeline end-to-end (ACTUATION_TARGET=sim); 229 existing tests pass, ruff clean, e2e_smoke.py proves the full PROPOSED->APPROVED->EXECUTING->DONE cycle with real ACTION+OUTCOME verifications over HTTP.
Concerns/Blockers: Startup recovery/retention and DB persistence of approvals/verifications/tasks/schedules were narrowed out of scope (documented above, reported honestly as BLOCKED_M1 rather than faked); sim's static WEATHER_01/SUN_01/PH_01/idle-TANK_01 will legitimately trigger stuck_at findings over a long-running dev session.
