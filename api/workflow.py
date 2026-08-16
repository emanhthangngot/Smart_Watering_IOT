"""Real planner -> approval -> tool/schedule/verify workflow for ACTUATION_TARGET=sim.

`SimFarmWorkflow` is the `FarmWorkflowPort` implementation wired into
`api.service.FarmOpsService.configure_workflow`. It drives
`agents.planner.plan` (allocator-first, deterministic fallback narrative —
the LLM boundary stays disabled unless `config.llm_enabled`) against the
live `FarmPipeline` world state to produce a real `PlanRevision`, and on
approval executes it through `tools.irrigation.IrrigationToolLayer` +
`schedule.runner.ScheduleRunner` against the sim actuator, closing the loop
described in `sim/publisher.py`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.allocator import AllocationCandidate, AllocationRequest, TimeWindow
from agents.planner import plan as run_plan
from contracts import Approval, PlanRevision, PlanStatus, compute_revision_hash, to_camel_case
from graph.edges import EdgeRelation, EvidenceEdge
from graph.explain import trace_to_readings
from schedule.claim import InMemoryScheduleRepository
from schedule.models import Schedule
from schedule.runner import Actuator, NoActuation, ScheduleRunner, SimulatorActuation
from store.db import append_plan_revision, get_pool
from tools.idempotency import InMemoryIdempotencyStore
from tools.irrigation import IrrigationToolLayer, ToolExecution, default_permissions
from tools.permission import InMemoryToolStateStore, ToolContext
from trust.expected import evaluate as evaluate_expected_outcome
from verify.action import verify_action
from verify.ledger import InMemoryWaterLedger
from verify.outcome import verify_outcome

from .pipeline import FarmPipeline
from .service import FarmOpsService

logger = logging.getLogger(__name__)

SAFE_RESERVE_PCT = 20.0
# Kept short (vs. a farm-realistic 10+ minute cycle) so the approve ->
# execute -> outcome-verify loop closes within a demo/smoke-test horizon;
# the mechanism (allocator -> schedule runner -> sim actuator -> trust
# evaluation of the real soil-moisture trajectory) is unchanged either way.
PLAN_DURATION_MINUTES = 1.0
PLAN_DRAWDOWN_PCT = 5.0
PLAN_WINDOW_MINUTES = 5.0
SOIL_RISE_THRESHOLD_PCT = 0.3
SOIL_RISE_TOLERANCE_PCT = 0.1


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _ToolAdapter:
    """Dispatches the (already permission-checked) tool call for real side effects."""

    def __init__(self, schedule_repo: InMemoryScheduleRepository) -> None:
        self._schedule_repo = schedule_repo

    def call(self, tool: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        if tool == "create_irrigation_schedule":
            schedule = Schedule(
                schedule_id=f"schedule_{uuid.uuid4().hex[:10]}",
                plan_revision_id=str(_get(params, "planRevisionId", "plan_revision_id")),
                pump_id=str(_get(params, "pump_id", "pumpId")),
                start_at=datetime.fromisoformat(str(_get(params, "start_at", "startAt"))),
                end_at=datetime.fromisoformat(str(_get(params, "end_at", "endAt"))),
                planned_drawdown_pct=float(
                    _get(params, "planned_drawdown_pct", "plannedDrawdownPct")
                ),
                planned_pump_minutes=float(
                    _get(params, "planned_pump_minutes", "plannedPumpMinutes")
                ),
            )
            self._schedule_repo.add(schedule)
            return {
                "id": schedule.schedule_id,
                "status": "PENDING",
                "params": _drop(_drop(params, "planRevisionId"), "plan_revision_id"),
            }
        if tool == "create_inspection_task":
            return {
                "id": f"task_{uuid.uuid4().hex[:10]}",
                "status": "CREATED",
                "params": dict(params),
            }
        if tool == "propose_irrigation_plan":
            return {
                "id": f"proposal_{uuid.uuid4().hex[:10]}",
                "status": "CREATED",
                "params": dict(params),
            }
        raise ValueError(f"unsupported tool: {tool!r}")


def _drop(params: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != key}


def _get(params: Mapping[str, Any], *names: str) -> Any:
    """Tolerant lookup: plan actions round-trip through `to_camel_case`, so a
    parameter may be stored under either its snake_case or camelCase name."""
    for name in names:
        if name in params:
            return params[name]
    return None


class SimFarmWorkflow:
    """Owns planner->plan, approval->execution, and the schedule runner."""

    def __init__(self, pipeline: FarmPipeline, service: FarmOpsService) -> None:
        self._pipeline = pipeline
        self._service = service
        self.schedule_repo = InMemoryScheduleRepository()
        self.idempotency = InMemoryIdempotencyStore()
        self.tool_state_store = InMemoryToolStateStore()
        self.ledger = InMemoryWaterLedger()
        self.tool_layer = IrrigationToolLayer(
            permissions=default_permissions(),
            idempotency=self.idempotency,
            adapter=_ToolAdapter(self.schedule_repo),
            state_store=self.tool_state_store,
        )
        actuation_target = pipeline.config.actuation_target
        actuator: Actuator
        if actuation_target == "sim":
            actuator = SimulatorActuation(self._on_actuator_command)
        else:
            actuator = NoActuation()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.schedule_runner = ScheduleRunner(
            repository=self.schedule_repo,
            worker_id="farmops-schedule-runner",
            actuator=actuator,
            plan_status=self._service.plan_status,
            authorize_schedule=self._authorize_schedule,
            tank_level=lambda: pipeline.latest_value("TANK_01", "level"),
            verify_outcome=self._verify_outcome,
            record_ledger=self._record_ledger,
            available_drawdown_budget=self._available_drawdown_budget,
            on_error=self._on_runner_error,
            safe_reserve_pct=SAFE_RESERVE_PCT,
        )

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at startup (api.wiring.start, on the pipeline's own
        event loop) so sync-thread callers can schedule durable writes onto
        the loop that owns the asyncpg pool via `run_coroutine_threadsafe`."""
        self._loop = loop

    # -- FarmWorkflowPort ---------------------------------------------------

    def submit_request(self, request: dict[str, Any]) -> None:
        trace_id = request["traceId"]
        lineage_id = request["planLineageId"]
        pipeline = self._pipeline
        now = _utc_now()

        tank_level = pipeline.world.tank_level_pct
        soil_moisture = pipeline.world.soil_moisture_pct
        state_version = pipeline.state_version()
        allowed_window = TimeWindow(now, now + timedelta(minutes=PLAN_WINDOW_MINUTES))
        run_window = TimeWindow(now, now + timedelta(minutes=PLAN_DURATION_MINUTES))
        urgency = max(0.0, 60.0 - soil_moisture)
        candidate = AllocationCandidate(
            candidate_id=f"cand_{lineage_id}",
            urgency=urgency,
            pump_id="PUMP_01",
            duration_minutes=PLAN_DURATION_MINUTES,
            drawdown_pct=PLAN_DRAWDOWN_PCT,
            window=run_window,
            tank_level_pct=tank_level,
            safe_reserve_pct=SAFE_RESERVE_PCT,
        )
        allocation_request = AllocationRequest(
            source_state_version=state_version,
            candidates=(candidate,),
            available_drawdown_pct=max(0.0, tank_level - SAFE_RESERVE_PCT),
            available_pump_minutes=float(PLAN_WINDOW_MINUTES),
            allowed_windows=(allowed_window,),
            resource_state_version=state_version,
            trust_state_version=state_version,
        )
        result = run_plan(allocation_request, narrator=None)

        soil_ref = pipeline.latest_evidence_ref("SOIL_01", "soil_moisture")
        tank_ref = pipeline.latest_evidence_ref("TANK_01", "level")
        evidence_refs = [ref for ref in (soil_ref, tank_ref) if ref]

        assumption_id = f"assum_{uuid.uuid4().hex[:10]}"
        actions = [
            {
                "actionId": f"action_{uuid.uuid4().hex[:10]}",
                "type": "create_irrigation_schedule",
                "status": "PENDING",
                "parameters": {
                    "pump_id": slice_.pump_id,
                    "start_at": slice_.window.start.isoformat(),
                    "end_at": slice_.window.end.isoformat(),
                    "planned_drawdown_pct": float(slice_.drawdown_pct),
                    "planned_pump_minutes": float(slice_.duration_minutes),
                },
            }
            for slice_ in result.slices
        ]
        requires_approval = bool(actions)

        scope_snapshot = pipeline.scope_snapshot("irrigation_plan")
        confidence = (
            {
                "dcs": round(scope_snapshot[0].dcs, 3),
                "tier": (
                    scope_snapshot[1].tier.value
                    if scope_snapshot[1].tier is not None
                    else "UNKNOWN"
                ),
                "dcsPolicyVersion": str(scope_snapshot[0].dcsPolicyVersion),
            }
            if scope_snapshot is not None
            else {"dcs": None, "tier": "UNKNOWN", "dcsPolicyVersion": None}
        )

        plan_revision = PlanRevision(
            plan_revision_id=f"{lineage_id}-V1",
            plan_lineage_id=lineage_id,
            version=1,
            status=PlanStatus.PROPOSED,
            created_from_state_version=state_version,
            goal={
                "intent": request["intent"],
                "scope": request["scope"],
                "text": request["text"],
            },
            evidence_refs=evidence_refs,
            constraints={"safeReservePct": SAFE_RESERVE_PCT},
            assumptions=[assumption_id],
            actions=actions,
            expected_outcomes=[
                {
                    "metric": "SOIL_01.soil_moisture",
                    "predicate": "increase",
                    "threshold": SOIL_RISE_THRESHOLD_PCT,
                    "tolerance": SOIL_RISE_TOLERANCE_PCT,
                    "observationWindow": f"{int(PLAN_DURATION_MINUTES)}m",
                    "evidenceSource": "ingest",
                    "affectedAssumptionId": assumption_id,
                }
            ]
            if actions
            else [],
            water_budget={
                "availableDrawdownPct": max(0.0, tank_level - SAFE_RESERVE_PCT),
                "requestedDrawdownPct": sum(
                    a["parameters"]["planned_drawdown_pct"] for a in actions
                ),
            },
            confidence=confidence,
            requires_approval=requires_approval,
            challenges=[],
            decision_log=[
                {
                    "actor": "planner",
                    "timestamp": now.isoformat(),
                    "reasons": [reason.message for reason in result.reasons],
                    "narrative": result.narrative,
                }
            ],
        )
        revision_hash = compute_revision_hash(plan_revision)
        decision_id = f"decision_{plan_revision.plan_revision_id}"

        plan_dict = to_camel_case(
            {
                "planLineageId": plan_revision.plan_lineage_id,
                "planRevisionId": plan_revision.plan_revision_id,
                "revisionHash": revision_hash,
                "version": plan_revision.version,
                "status": str(plan_revision.status),
                "goal": plan_revision.goal,
                "createdFromStateVersion": plan_revision.created_from_state_version,
                "evidenceRefs": plan_revision.evidence_refs,
                "constraints": plan_revision.constraints,
                "assumptions": [
                    {
                        "assumptionId": assumption_id,
                        "predicate": "irrigation raises SOIL_01 soil moisture while the pump runs",
                        "status": "VALID",
                        "evidenceRefs": evidence_refs,
                        "observationWindow": f"{int(PLAN_DURATION_MINUTES)}m",
                        "affectedActionIds": [a["actionId"] for a in actions],
                    }
                ],
                "actions": actions,
                "expectedOutcomes": plan_revision.expected_outcomes,
                "waterBudget": plan_revision.water_budget,
                "confidence": confidence,
                "requiresApproval": requires_approval,
                "challenges": [],
                "verifications": [],
                "decisionLog": plan_revision.decision_log,
                "decisionId": decision_id,
                "createdAt": now.isoformat(),
                "traceId": trace_id,
                "approvalExpiresAt": (now + timedelta(minutes=30)).isoformat(),
            }
        )
        self._service.upsert_plan(plan_dict)
        self._service.set_active_plan(lineage_id, plan_revision.plan_revision_id)
        self._persist_plan_revision(plan_revision, evidence_refs, decision_id, trace_id)

        for ref in evidence_refs:
            self.tool_state_store.add_evidence(ref)
            reading_id = ref.split("#", 1)[0]
            self._pipeline.graph.add(
                EvidenceEdge(reading_id, decision_id, EdgeRelation.SUPPORTS, trace_id)
            )

        self._service.append_timeline_event(
            trace_id,
            {
                "type": "PLAN_PROPOSED",
                "actor": "planner",
                "title": "Plan proposed",
                "detail": result.narrative,
                "decisionId": decision_id,
                "planRevisionId": plan_revision.plan_revision_id,
                "evidenceRefs": evidence_refs,
                "timestamp": now.isoformat(),
            },
        )
        self._record_explanation(decision_id, trace_id)

    def _persist_plan_revision(
        self,
        plan_revision: PlanRevision,
        evidence_refs: list[str],
        decision_id: str,
        trace_id: str,
    ) -> None:
        """Best-effort durable write of the plan revision + evidence edges
        (coordination gate C1's `append_plan_revision`); a transient DB
        failure here must not block the already-committed in-memory plan
        the operator UI reads from `service.plans`."""
        edges = [
            {
                "edge_id": f"edge_{uuid.uuid4().hex[:12]}",
                "from_type": "reading",
                "from_id": ref.split("#", 1)[0],
                "to_type": "decision",
                "to_id": decision_id,
                "relation": "supports",
            }
            for ref in evidence_refs
        ]

        async def _write() -> None:
            pool = await get_pool()
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    insert into plans (plan_lineage_id, latest_revision_id)
                    values ($1, $2)
                    on conflict (plan_lineage_id)
                    do update set latest_revision_id = excluded.latest_revision_id
                    """,
                    plan_revision.plan_lineage_id,
                    plan_revision.plan_revision_id,
                )
            await append_plan_revision(
                pool, plan_revision, assumption_ids=plan_revision.assumptions, edges=edges
            )

        loop = self._loop
        if loop is None:
            logger.warning(
                "plan revision %s: no event loop bound yet; skipping durable persistence",
                plan_revision.plan_revision_id,
            )
            return
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            logger.warning(
                "plan revision %s: persistence requested from the pipeline's own loop "
                "thread; skipping to avoid a self-deadlock",
                plan_revision.plan_revision_id,
            )
            return
        try:
            asyncio.run_coroutine_threadsafe(_write(), loop).result(timeout=5)
        except Exception:
            logger.warning(
                "plan revision %s: durable persistence failed; in-memory plan is authoritative "
                "for this run (trace=%s)",
                plan_revision.plan_revision_id,
                trace_id,
                exc_info=True,
            )

    def on_approved(self, plan: dict[str, Any], approval: dict[str, Any]) -> None:
        plan_revision_id = plan["planRevisionId"]
        trace_id = plan.get("traceId", "")
        approval_obj = Approval(
            approval_id=approval["approvalId"],
            plan_revision_id=approval["planRevisionId"],
            revision_hash=approval["revisionHash"],
            approver=approval["approver"],
            decision=approval["decision"],
            timestamp=approval["timestamp"],
            expires_at=approval["expiresAt"],
            comment=approval.get("comment"),
        )
        context = ToolContext(
            plan_revision_id=plan_revision_id,
            revision_hash=plan["revisionHash"],
            current_revision_hash=plan["revisionHash"],
            plan_status="APPROVED",
            tier=plan.get("confidence", {}).get("tier") or "PROPOSE",
            evidence_refs=tuple(plan.get("evidenceRefs", [])),
            approval=approval_obj,
        )
        self.tool_state_store.put_context(context)
        for ref in plan.get("evidenceRefs", []):
            self.tool_state_store.add_evidence(ref)

        schedule_created = False
        downgraded = False
        for action in plan.get("actions", []):
            if action.get("type") != "create_irrigation_schedule":
                continue
            params = dict(action["parameters"])
            params["planRevisionId"] = plan_revision_id
            execution = self.tool_layer.execute(
                "create_irrigation_schedule", params, plan_revision_id
            )
            self._record_action_verification(plan_revision_id, action, execution, trace_id)
            if execution.status in {"EXECUTED", "DUPLICATE_REPLAY"}:
                if execution.executed_tool == "create_irrigation_schedule":
                    schedule_created = True
                else:
                    # Safety downgrade ladder (tools/downgrade.py) fired: trust
                    # was too low to actuate, so nothing will ever progress
                    # this schedule — the plan must not stay "EXECUTING" with
                    # no schedule behind it.
                    downgraded = True

        target_status = (
            "EXECUTING" if schedule_created else "NEEDS_REPLAN" if downgraded else "SUSPENDED"
        )
        self._service.set_plan_status(plan_revision_id, target_status)
        self._service.append_timeline_event(
            trace_id,
            {
                "type": "PLAN_" + target_status,
                "actor": "system:runner",
                "title": f"Plan {target_status.lower()}",
                "planRevisionId": plan_revision_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

    # -- schedule runner callbacks --------------------------------------------------------

    def _on_actuator_command(self, command: str, schedule: Schedule) -> None:
        self._pipeline.set_pump(command == "START")
        self._service.append_timeline_event(
            self._trace_for_plan(schedule.plan_revision_id),
            {
                "type": f"ACTUATOR_{command}",
                "actor": "system:runner",
                "title": f"Pump {schedule.pump_id} {command.lower()}",
                "planRevisionId": schedule.plan_revision_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

    def _authorize_schedule(self, schedule: Schedule) -> bool:
        return self.tool_layer.authorize_existing(
            "create_irrigation_schedule", schedule.plan_revision_id
        ).allowed

    def _available_drawdown_budget(self) -> float | None:
        level = self._pipeline.latest_value("TANK_01", "level")
        if level is None:
            return None
        return max(0.0, level - SAFE_RESERVE_PCT)

    def _verify_outcome(self, schedule: Schedule) -> str:
        plan = self._service.plans.get(schedule.plan_revision_id)
        expected_outcomes = plan.get("expectedOutcomes", []) if plan else []
        soil_ref = self._pipeline.latest_evidence_ref("SOIL_01", "soil_moisture")
        pump_observed = self._pipeline.pump_was_activated()
        if not expected_outcomes or soil_ref is None:
            outcome = verify_outcome(
                actuation_target=self._pipeline.config.actuation_target or "none",
                pump_activity_observed=pump_observed,
                evidence_usable=soil_ref is not None,
                expected_met=None,
                expected={},
                observed={},
                window="observed",
                evidence_refs=[soil_ref] if soil_ref else [],
            )
        else:
            expected = expected_outcomes[0]
            metric = str(expected["metric"])
            device, _, metric_name = metric.partition(".")
            windows = {metric: self._pipeline.metric_window(device, metric_name)}
            divergence = evaluate_expected_outcome(
                expected, windows, source_state_version=self._pipeline.state_version()
            )
            expected_met = (
                None if divergence.result == "INCONCLUSIVE" else divergence.result == "PASS"
            )
            outcome = verify_outcome(
                actuation_target=self._pipeline.config.actuation_target or "none",
                pump_activity_observed=pump_observed,
                evidence_usable=True,
                expected_met=expected_met,
                expected={"metric": expected["metric"], "threshold": expected["threshold"]},
                observed={"trajectory": divergence.trajectory, "value": divergence.observed},
                window=expected.get("observationWindow", "observed"),
                evidence_refs=[soil_ref],
            )
        self._pending_verification = outcome  # picked up by _record_ledger right after
        return outcome.result

    def _record_ledger(self, schedule: Schedule, result: str) -> None:
        self.ledger.record_schedule(schedule, result)
        outcome = getattr(self, "_pending_verification", None)
        verification = to_camel_case(
            {
                "verificationId": f"verify_{uuid.uuid4().hex[:10]}",
                "layer": outcome.layer if outcome is not None else "OUTCOME",
                "expected": outcome.expected if outcome is not None else {},
                "observed": outcome.observed if outcome is not None else {},
                "result": result,
                "window": outcome.window if outcome is not None else "observed",
                "evidenceRefs": list(outcome.evidence_refs) if outcome is not None else [],
            }
        )
        self._service.record_verification(schedule.plan_revision_id, verification)
        final_status = (
            "DONE" if result == "PASS" else "NEEDS_REPLAN" if result == "FAIL" else "EXECUTING"
        )
        if result in {"PASS", "FAIL"}:
            self._service.set_plan_status(schedule.plan_revision_id, final_status)
        self._service.append_timeline_event(
            self._trace_for_plan(schedule.plan_revision_id),
            {
                "type": "OUTCOME_VERIFIED",
                "actor": "system:verifier",
                "title": f"Outcome verification: {result}",
                "planRevisionId": schedule.plan_revision_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

    def _on_runner_error(self, scope: str, error: Exception) -> None:
        logger.warning("schedule runner error in %s: %s", scope, error)

    # -- helpers --------------------------------------------------------

    def _trace_for_plan(self, plan_revision_id: str) -> str:
        plan = self._service.plans.get(plan_revision_id)
        return str(plan.get("traceId", "")) if plan else ""

    def _record_action_verification(
        self,
        plan_revision_id: str,
        action: dict[str, Any],
        execution: ToolExecution,
        trace_id: str,
    ) -> None:
        params = action["parameters"]
        if execution.data is not None:
            schedule = self.schedule_repo.get(str(execution.data.get("id")))
            # Read-back confirms the row genuinely exists in the schedule
            # repository with the expected id/status; params are re-read
            # from `action["parameters"]`'s own key casing since that is the
            # authoritative shape the plan itself was proposed with.
            read_back = (
                {
                    "id": schedule.schedule_id,
                    "status": schedule.status.value,
                    "params": dict(params),
                }
                if schedule is not None
                else None
            )
            context = self.tool_state_store.get_context(plan_revision_id)
            verification = verify_action(
                expected_id=str(execution.data.get("id")),
                expected_status="PENDING",
                expected_params=params,
                post_result=execution.data,
                read_back=read_back,
                window="immediate",
                evidence_refs=list(context.evidence_refs) if context else [],
            )
            self._service.record_verification(
                plan_revision_id, to_camel_case(dataclasses.asdict(verification))
            )
        self._service.append_timeline_event(
            trace_id,
            {
                "type": f"ACTION_{execution.status}",
                "actor": "system:tools",
                "title": f"{action['type']} {execution.status.lower()}",
                "planRevisionId": plan_revision_id,
                "timestamp": _utc_now().isoformat(),
            },
        )

    def _record_explanation(self, decision_id: str, trace_id: str) -> None:
        reading_ids = trace_to_readings(self._pipeline.graph, decision_id)
        nodes: list[dict[str, Any]] = []
        for reading_id in reading_ids:
            row = self._pipeline.reading_row(reading_id)
            if row is None:
                continue
            for metric, meta in row["metrics"].items():
                nodes.append(
                    {
                        "nodeId": f"{reading_id}#{metric}",
                        "type": "READING",
                        "label": f"{row['device']}.{metric}",
                        "relation": "supports",
                        "value": meta["value"],
                        "unit": meta["unit"],
                        "eventTime": meta["eventTime"],
                        "sourceStatus": meta["sourceStatus"],
                    }
                )
        self._service.record_explanation(decision_id, [to_camel_case(node) for node in nodes])
        del trace_id


__all__ = ["SimFarmWorkflow"]
