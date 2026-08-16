"""Composition root for infrastructure that already has a durable, tested
adapter. Owner: dev (this file wires other owners' modules together; it
must not add business logic of its own — see plans/reports/plan.md §13.3).

Scope, explicit:

Wired here — the schedule runner (plan.md §9.1):
  - store.schedule_repository.PostgresScheduleRepository (already merged,
    coordination gate C4) for durable, cross-restart-safe claim/transition.
  - api.service.service's existing in-memory plan/approval state as the
    plan_status/authorize_schedule source — /approvals/* already writes
    there; this just reads it instead of duplicating it.
  - a small live tank-level cache refreshed from
    store.read_model.PostgresFarmStateRepository. The runner's callbacks
    are synchronous (called from inside ScheduleRunner.tick()); the DB
    read is async, so a background poll loop bridges the two rather than
    making the runner async (schedule/runner.py is intentionally sync).

Deliberately NOT wired here, and why:
  - Startup recovery (api.recovery.recover): RecoveryPort requires
    reattach_plan_monitor / reevaluate_assumptions / expire_approval_and_plan
    — all three assume a live plan-monitor/agent loop reacting to state.
    That loop does not exist yet: agents/coordinator.py is a pure route()
    function over pre-built RouteSignals, not an orchestrator that reads
    live World State. Building it is a feature (crosses M1 read-model +
    M2 trust + M3 agents), not glue — do not improvise it here.
  - Retention (api.retention.run_retention): RetentionPort has no Postgres
    implementation at all (no rollup_before/delete_sensor_batch adapter,
    no readings_hourly table in store/schema.sql). M1 gap, not a wiring gap.
  - FarmWorkflowPort (/farm/request -> agent pipeline): needs the same
    missing "evidence bundle -> AllocationCandidate/ResourceInput"
    translation layer as recovery above (no module builds these from live
    readings today). Left as BLOCKED_DEPENDENCY until that layer exists.

Because of this, the schedule runner will tick over an empty table until
a real workflow starts writing schedules — same "empty queue is normal"
shape as the ingestion outbox. Wiring it now is still worth doing: it is
real, tested infrastructure, and the next piece (once FarmWorkflowPort
exists) plugs straight into `service.plans` / `service.approvals` with no
further runtime changes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from api.service import FarmOpsService
from config import Config
from schedule.claim import ScheduleRepository
from schedule.models import Schedule
from schedule.runner import ScheduleRunner, actuator_for
from store.read_model import PostgresFarmStateRepository
from store.schedule_repository import PostgresScheduleRepository
from verify.ledger import InMemoryWaterLedger
from verify.outcome import verify_outcome

logger = logging.getLogger(__name__)

TANK_DEVICE = "TANK_01"
TANK_METRIC = "level"
TANK_POLL_SECONDS = 5.0
# Matches schedule.runner.ScheduleRunner's own default; no Config field
# exists yet for this (plan.md §18 open question 6 is still unresolved).
SAFE_RESERVE_PCT_DEFAULT = 20.0


class _TankLevelCache:
    """Bridges the runner's sync tank_level() callback to the async DB read."""

    def __init__(self, read_model: PostgresFarmStateRepository) -> None:
        self._read_model = read_model
        self._value: float | None = None

    def get(self) -> float | None:
        return self._value

    async def poll_forever(self) -> None:
        while True:
            try:
                snapshot = await self._read_model.snapshot()
                self._value = _extract_fresh_tank_level(snapshot)
            except Exception as error:
                logger.warning("tank level poll failed: %s", type(error).__name__)
                self._value = None
            await asyncio.sleep(TANK_POLL_SECONDS)


def _extract_fresh_tank_level(snapshot: dict[str, Any]) -> float | None:
    # Only FRESH counts as usable evidence (plan.md §3.3) — a STALE or
    # missing tank reading must not silently authorize a drawdown.
    for device in snapshot.get("devices", []):
        if device.get("deviceCode") != TANK_DEVICE:
            continue
        metric = device.get("metrics", {}).get(TANK_METRIC)
        if metric and metric.get("state") == "FRESH" and metric.get("value") is not None:
            return float(metric["value"])
    return None


def authorize_schedule(service: FarmOpsService, schedule: Schedule) -> bool:
    """Fail-closed: only an unexpired APPROVE for the schedule's plan,
    matching that plan's current revision hash, authorizes it (INV-6)."""
    plan = service.plans.get(schedule.plan_revision_id)
    if plan is None:
        return False
    now = datetime.now(UTC)
    for approval in service.approvals.values():
        if approval.get("planRevisionId") != schedule.plan_revision_id:
            continue
        if approval.get("decision") != "APPROVE":
            continue
        if approval.get("revisionHash") != plan.get("revisionHash"):
            continue
        expires_at = approval.get("expiresAt")
        if expires_at:
            parsed = datetime.fromisoformat(expires_at)
            if parsed <= now:
                continue
        return True
    return False


class ScheduleRunnerBootstrap:
    """Satisfies api.runtime.ForeverRunner: runs the schedule runner and
    its tank-level poll loop together as one background task."""

    def __init__(self, runner: ScheduleRunner, tank_cache: _TankLevelCache) -> None:
        self.runner = runner
        self._tank_cache = tank_cache

    async def run_forever(self) -> None:
        await asyncio.gather(self.runner.run_forever(), self._tank_cache.poll_forever())


def build_schedule_runner(
    config: Config, service: FarmOpsService
) -> ScheduleRunnerBootstrap | None:
    """Best-effort, like the data-plane wiring in api/main.py: returns None
    instead of raising if Postgres isn't reachable at construction time, so
    a slow/absent DB never blocks the API from starting."""
    # actuator_for("sim") needs a simulator command adapter this bootstrap
    # does not construct (api/simulator.py's adapter is only wired for the
    # /sim/* control endpoints, not schedule playback yet); fail closed to
    # "none" (observation-only) rather than crash startup or pretend to
    # control a pump we can't reach. Used consistently below so the
    # actuator and the outcome-verification semantics never disagree.
    effective_actuation_target = "none" if config.actuation_target == "sim" else config.actuation_target
    try:
        repository: ScheduleRepository = PostgresScheduleRepository()
        actuator = actuator_for(effective_actuation_target)
    except Exception as error:
        logger.warning(
            "schedule runner disabled, postgres unavailable: %s", type(error).__name__
        )
        return None

    read_model = PostgresFarmStateRepository(config.team_code)
    tank_cache = _TankLevelCache(read_model)
    ledger = InMemoryWaterLedger()  # not durable yet — see module docstring

    def observational_outcome(schedule: Schedule) -> str:
        # Always INCONCLUSIVE by construction (empty evidence_refs): no
        # grounded reading id is threaded through here yet, and
        # verify_outcome treats missing evidence_refs as unusable rather
        # than fabricating a PASS/FAIL — see verify/outcome.py. Once a
        # workflow produces real expectedOutcome records this should read
        # actual soil/flow deltas instead.
        del schedule
        return verify_outcome(
            actuation_target=effective_actuation_target,
            pump_activity_observed=False,
            evidence_usable=tank_cache.get() is not None,
            expected_met=None,
            expected={"soil_delta": ">0"},
            observed={"pumpActivity": False},
            window="scheduled",
            evidence_refs=[],
        ).result

    def available_drawdown_budget() -> float | None:
        level = tank_cache.get()
        if level is None:
            return None
        return max(0.0, level - SAFE_RESERVE_PCT_DEFAULT)

    runner = ScheduleRunner(
        repository=repository,
        worker_id=f"runner-{uuid4().hex[:8]}",
        actuator=actuator,
        plan_status=service.plan_status,
        authorize_schedule=lambda schedule: authorize_schedule(service, schedule),
        tank_level=tank_cache.get,
        verify_outcome=observational_outcome,
        record_ledger=ledger.record_schedule,
        available_drawdown_budget=available_drawdown_budget,
        safe_reserve_pct=SAFE_RESERVE_PCT_DEFAULT,
        on_error=lambda schedule_id, error: logger.warning(
            "schedule runner error on %s: %s", schedule_id, type(error).__name__
        ),
    )
    return ScheduleRunnerBootstrap(runner, tank_cache)


__all__ = ["ScheduleRunnerBootstrap", "authorize_schedule", "build_schedule_runner"]
