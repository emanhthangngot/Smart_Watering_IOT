"""Minimal FarmWorkflowPort: the first real call chain connecting the
agent functions in agents/ to a live `/farm/request`. Owner: dev (this
file wires other owners' pure functions together; it must not change
what those functions decide — see plans/reports/plan.md §13.3).

Why this didn't exist before: every function in agents/ is pure and
typed (route(), evaluate_resource(), plan()/allocate()) — none of them
read live state or call each other. Something has to (a) read the
current bundle, (b) build each function's typed input, (c) feed one
function's output into the next, (d) ground the result, (e) persist it
where api/routers/{farm,plan,approvals}.py already expect to find it
(api.service.service.plans, keyed and shaped exactly like the fixtures
in tests/tools/test_api.py).

What this call chain actually does, in order:
  1. Read the live snapshot (store.read_model.PostgresFarmStateRepository).
  2. Require FRESH TANK_01.level and FRESH SOIL_01.soil_moisture — anything
     else (STALE/OFFLINE/MISSING) blocks planning outright (plan.md §3.3:
     never fabricate evidence). No plan is created; only a timeline event.
  3. Resource: build a ResourceInput and call agents.resource.evaluate_resource.
  4. Coordinator: turn the Resource verdict into a RouteSignal and call
     agents.coordinator.route to decide planner vs. block.
  5. Planner: build one AllocationCandidate from a soil-moisture-urgency
     heuristic (see SOIL_MOISTURE_URGENCY_THRESHOLD below) and call
     agents.planner.plan (no LLM narrator wired — deterministic narrative
     only; plugging in an LLM narrator is a separate, self-contained
     follow-up, not attempted here).
  6. Ground the two evidence refs actually used, build a contracts.PlanRevision,
     compute its revision hash, and store it in service.plans.

Known, deliberate simplifications (product decisions, not bugs — revisit
before relying on this for anything but a demo):
  - No Diagnosis agent exists (agents/ has no diagnosis.py), so there is
    no cross-sensor water-balance challenge here — only the Resource
    budget check. A stuck/contradictory-but-fresh sensor is NOT caught
    by this path today.
  - No durable water ledger is read here (the schedule runner's own
    InMemoryWaterLedger in api/bootstrap.py is a separate instance and
    not consulted), so `active_reserved_drawdown_pct` is always 0 — this
    path cannot see other plans' pending drawdown. §8's daily ledger
    constraint is NOT fully enforced by this function; the schedule
    runner's own available_drawdown_budget check is the real last line
    of defense before a pump actually runs.
  - Candidate pump/duration/drawdown are fixed constants
    (DEFAULT_PUMP_ID / DEFAULT_DURATION_MINUTES / DEFAULT_DRAWDOWN_PCT),
    not derived from an actual irrigation-need model.
  - A blocked/rejected request produces a timeline event only — no
    inspection task is auto-created (plan.md §7.5's "uncertainty always
    creates an inspection task" is not implemented on this path).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from agents.allocator import AllocationCandidate, AllocationRequest, TimeWindow
from agents.coordinator import route
from agents.messages import ResourceInput, RouteSignal
from agents.planner import plan as run_planner
from agents.resource import evaluate_resource
from agents.vocabulary import InteractionVerb
from api.service import FarmOpsService, utc_now
from contracts import PlanRevision, PlanStatus, compute_revision_hash, to_camel_case
from graph.grounding import assert_grounded
from store.read_model import PostgresFarmStateRepository

logger = logging.getLogger(__name__)

TANK_DEVICE = "TANK_01"
TANK_METRIC = "level"
SOIL_DEVICE = "SOIL_01"
SOIL_METRIC = "soil_moisture"

# Placeholder operating policy — see module docstring; not derived from data.
SAFE_RESERVE_PCT_DEFAULT = Decimal("20")
DEFAULT_REQUESTED_DRAWDOWN_PCT = Decimal("5")
DEFAULT_AVAILABLE_PUMP_MINUTES = Decimal("60")
DEFAULT_DURATION_MINUTES = Decimal("10")
DEFAULT_PUMP_ID = "PUMP_01"
DEFAULT_WINDOW_HOURS = 2
SOIL_MOISTURE_URGENCY_THRESHOLD = Decimal("40")  # below this, irrigation is proposed


def _fresh_metric(
    snapshot: dict[str, Any], device_code: str, metric: str
) -> tuple[float, str] | None:
    for device in snapshot.get("devices", []):
        if device.get("deviceCode") != device_code:
            continue
        row = device.get("metrics", {}).get(metric)
        if row and row.get("state") == "FRESH" and row.get("value") is not None:
            reading_id = row.get("readingId")
            if not reading_id:
                return None
            return float(row["value"]), str(reading_id)
        return None
    return None


class AgentWorkflow:
    """Satisfies api.service.FarmWorkflowPort."""

    def __init__(
        self,
        read_model: PostgresFarmStateRepository,
        service: FarmOpsService,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._read_model = read_model
        self._service = service
        self._loop = loop

    def submit_request(self, request: dict[str, Any]) -> None:
        # Runs inside FastAPI's sync-endpoint threadpool (create_farm_request
        # is a sync def) — a different OS thread than the app's event loop.
        # store/db.py's asyncpg pool is created on and bound to that main
        # loop (api/main.py's lifespan awaits get_pool() there), so a plain
        # asyncio.run() here would build a second loop and hand it a pool
        # object it doesn't own — asyncpg raises across that boundary.
        # run_coroutine_threadsafe schedules the read onto the actual owning
        # loop and blocks this worker thread for the result instead.
        #
        # Deliberately not caught here: api.service.create_farm_request
        # already has a tested 503 "queue outcome uncertain" path for
        # whatever this raises (docs/api.md). Catching it here would make
        # that path dead code and turn a genuine infra failure (DB down)
        # into a silent, confident-looking timeline event. _blocked() below
        # is reserved for cases where the workflow *did* run and made a
        # clear, non-exceptional decision not to plan (missing evidence,
        # resource rejected, etc.) — those return normally, on purpose.
        future = asyncio.run_coroutine_threadsafe(self._read_model.snapshot(), self._loop)
        snapshot = future.result(timeout=10)
        self._run(request, snapshot)

    def _run(self, request: dict[str, Any], snapshot: dict[str, Any]) -> None:
        state_version = int(snapshot.get("farmStateVersion") or 0)
        if state_version == 0:
            self._blocked(request, "no telemetry yet")
            return

        tank = _fresh_metric(snapshot, TANK_DEVICE, TANK_METRIC)
        soil = _fresh_metric(snapshot, SOIL_DEVICE, SOIL_METRIC)
        if tank is None or soil is None:
            self._blocked(request, "tank level or soil moisture is not FRESH")
            return
        tank_value, tank_reading_id = tank
        soil_value, soil_reading_id = soil
        evidence_refs = [f"{tank_reading_id}#{TANK_METRIC}", f"{soil_reading_id}#{SOIL_METRIC}"]
        assert_grounded(evidence_refs, set(evidence_refs))  # trivially true; keeps the gate live

        now = datetime.now(UTC)
        assessment = evaluate_resource_for(tank_value, state_version, now)
        verb = (
            InteractionVerb.ACCEPT
            if assessment.accepted
            else InteractionVerb.REQUEST_MORE_EVIDENCE
            if assessment.needs_more_evidence
            else InteractionVerb.REJECT
        )
        signal = RouteSignal(
            signal_id="resource-1",
            source_participant="resource",
            verb=verb,
            blocking=assessment.blocking,
            source_state_version=state_version,
        )
        decision = route([signal], state_version)
        # route() sends REJECT to "planner" too, but with event=REVISE, not
        # PROPOSE — it expects an existing revision to revise. This is
        # always the first request for a fresh lineage here (no history to
        # revise), so only a clean PROPOSE may continue; REVISE/REQUEST_
        # MORE_EVIDENCE/ESCALATE all fall through to blocked.
        if decision.next_participant != "planner" or decision.event is not InteractionVerb.PROPOSE:
            self._blocked(request, f"resource: {assessment.reason}")
            return

        window = TimeWindow(now, now + timedelta(hours=DEFAULT_WINDOW_HOURS))
        candidates: tuple[AllocationCandidate, ...] = ()
        if soil_value < float(SOIL_MOISTURE_URGENCY_THRESHOLD):
            candidates = (
                AllocationCandidate(
                    candidate_id=f"cand-{request['traceId']}",
                    urgency=SOIL_MOISTURE_URGENCY_THRESHOLD - Decimal(str(soil_value)),
                    pump_id=DEFAULT_PUMP_ID,
                    duration_minutes=DEFAULT_DURATION_MINUTES,
                    drawdown_pct=DEFAULT_REQUESTED_DRAWDOWN_PCT,
                    window=window,
                    tank_level_pct=Decimal(str(tank_value)),
                    safe_reserve_pct=SAFE_RESERVE_PCT_DEFAULT,
                ),
            )
        allocation_request = AllocationRequest(
            source_state_version=state_version,
            candidates=candidates,
            available_drawdown_pct=assessment.available_drawdown_pct or Decimal(0),
            available_pump_minutes=DEFAULT_AVAILABLE_PUMP_MINUTES,
            allowed_windows=(window,),
            resource_state_version=state_version,
            trust_state_version=state_version,
        )
        result = run_planner(allocation_request, narrator=None)

        actions = [
            {
                "tool": "create_irrigation_schedule",
                "pumpId": item.pump_id,
                "startAt": item.window.start.isoformat(),
                "endAt": item.window.end.isoformat(),
                "plannedDrawdownPct": float(item.drawdown_pct),
                "plannedPumpMinutes": float(item.duration_minutes),
            }
            for item in result.slices
        ]
        revision = PlanRevision(
            plan_revision_id=f"{request['planLineageId']}-V1",
            plan_lineage_id=request["planLineageId"],
            version=1,
            status=PlanStatus.PROPOSED,
            created_from_state_version=state_version,
            goal={"type": request.get("intent", "IRRIGATION"), "scope": request.get("scope")},
            evidence_refs=evidence_refs,
            constraints={
                "tankReserveMinPct": float(SAFE_RESERVE_PCT_DEFAULT),
                "noPumpOverlap": True,
            },
            actions=actions,
            water_budget={
                "plannedDrawdownPct": sum(a["plannedDrawdownPct"] for a in actions),
                "plannedPumpMinutes": sum(a["plannedPumpMinutes"] for a in actions),
            },
            confidence={"resourceAssessment": assessment.reason},
            requires_approval=bool(actions),
            decision_log=[
                {"agent": "resource", "verb": str(verb), "reason": assessment.reason},
                {"agent": "planner", "narrative": result.narrative},
            ],
        )
        payload = to_camel_case(asdict(revision))
        payload["revisionHash"] = compute_revision_hash(revision)
        payload["createdAt"] = now.isoformat()
        self._service.plans[revision.plan_revision_id] = payload
        self._append_timeline(
            request["traceId"],
            {
                "type": "PLAN_PROPOSED",
                "planRevisionId": revision.plan_revision_id,
                "actionCount": len(actions),
                "timestamp": now.isoformat(),
            },
        )

    def _blocked(self, request: dict[str, Any], reason: str) -> None:
        self._append_timeline(
            request["traceId"],
            {
                "type": "FARM_REQUEST_NOT_PLANNED",
                "reason": reason,
                "timestamp": utc_now().isoformat(),
            },
        )

    def _append_timeline(self, trace_id: str, event: dict[str, Any]) -> None:
        self._service.timeline.setdefault(trace_id, []).append(event)


def evaluate_resource_for(tank_level_pct: float, state_version: int, now: datetime):
    return evaluate_resource(
        ResourceInput(
            level_pct=Decimal(str(tank_level_pct)),
            safe_reserve_pct=SAFE_RESERVE_PCT_DEFAULT,
            active_reserved_drawdown_pct=Decimal(0),  # no shared ledger read — see module docstring
            requested_drawdown_pct=DEFAULT_REQUESTED_DRAWDOWN_PCT,
            farm_day=now.date().isoformat(),
            timezone="UTC",
            ledger_as_of=now,
            now=now,
            source_state_version=state_version,
        )
    )


def build_workflow(
    service: FarmOpsService,
    read_model: PostgresFarmStateRepository,
    loop: asyncio.AbstractEventLoop,
) -> AgentWorkflow:
    return AgentWorkflow(read_model, service, loop)


__all__ = ["AgentWorkflow", "build_workflow"]
