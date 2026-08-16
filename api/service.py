"""Thread-safe local state façade until M1/M3 persistence services land."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from fastapi import HTTPException, status

from tools.idempotency import IdempotencyStore

from .auth import OperatorIdentity
from .simulator import (
    SimulatorAdapter,
    SimulatorCommandInProgress,
    SimulatorControlGate,
)


class FarmWorkflowPort(Protocol):
    def submit_request(self, request: dict[str, Any]) -> None: ...

    def on_approved(self, plan: dict[str, Any], approval: dict[str, Any]) -> None:
        """Optional: called after a plan is APPROVEd, before the HTTP response
        returns. Absent on workflows that do not execute anything on approval."""


class TelemetryPort(Protocol):
    """Read-only façade the real `FarmPipeline` implements (api/pipeline.py)."""

    def health_snapshot(self) -> dict[str, Any]: ...

    def farm_state_snapshot(self) -> dict[str, Any]: ...

    def scope_verdicts(self) -> list[dict[str, Any]]: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class FarmOpsService:
    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self._lock = threading.RLock()
        self.requests: dict[str, dict[str, Any]] = {}
        self.plans: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.timeline: dict[str, list[dict[str, Any]]] = {}
        self.explanations: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        self.simulator_control: SimulatorControlGate | None = None
        self.workflow: FarmWorkflowPort | None = None
        self.telemetry: TelemetryPort | None = None
        self.active_plans: dict[str, str] = {}  # plan_lineage_id -> plan_revision_id

    def create_farm_request(
        self,
        *,
        intent: str,
        scope: str,
        text: str,
        operator: OperatorIdentity,
    ) -> dict[str, str]:
        with self._lock:
            trace_id = f"trace_{uuid.uuid4().hex[:10]}"
            lineage_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
            record = {
                "traceId": trace_id,
                "planLineageId": lineage_id,
                "intent": intent,
                "scope": scope,
                "text": text,
                "status": "QUEUING" if self.workflow is not None else "BLOCKED_DEPENDENCY",
                "createdAt": utc_now().isoformat(),
            }
            self.requests[trace_id] = record
            self.timeline[trace_id] = [{"type": "FARM_REQUESTED", **record}]
            self._audit("farm.request", operator, {"traceId": trace_id})
            workflow = self.workflow
            if workflow is None:
                self.timeline[trace_id].append(
                    {
                        "type": "FARM_REQUEST_BLOCKED",
                        "reason": "agent workflow unavailable",
                        "timestamp": utc_now().isoformat(),
                    }
                )
                return {"traceId": trace_id, "planLineageId": lineage_id}
            submitted = copy.deepcopy(record)
        try:
            workflow.submit_request(submitted)
        except Exception as error:
            with self._lock:
                record["status"] = "QUEUE_OUTCOME_UNCERTAIN"
                self.timeline[trace_id].append(
                    {
                        "type": "FARM_REQUEST_QUEUE_UNCERTAIN",
                        "timestamp": utc_now().isoformat(),
                    }
                )
                self._audit("farm.request.queue_uncertain", operator, {"traceId": trace_id})
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"workflow queue outcome uncertain for trace {trace_id}; inspect timeline",
            ) from error
        with self._lock:
            record["status"] = "ACCEPTED"
            self.timeline[trace_id].append(
                {"type": "FARM_REQUEST_ACCEPTED", "timestamp": utc_now().isoformat()}
            )
            self._audit("farm.request.accepted", operator, {"traceId": trace_id})
        return {"traceId": trace_id, "planLineageId": lineage_id}

    def farm_state(self) -> dict[str, Any]:
        with self._lock:
            telemetry = self.telemetry.farm_state_snapshot() if self.telemetry is not None else {}
            active_plan = None
            for lineage_id, revision_id in self.active_plans.items():
                plan = self.plans.get(revision_id)
                if plan is not None and plan.get("status") in {"PROPOSED", "APPROVED", "EXECUTING"}:
                    active_plan = {"planLineageId": lineage_id, "planRevisionId": revision_id}
            return {
                "status": "PARTIAL" if self.telemetry is None else "OK",
                "farmStateVersion": telemetry.get("farmStateVersion", 0),
                "updatedAt": telemetry.get("updatedAt"),
                "devices": telemetry.get("devices", []),
                "evidenceHealth": telemetry.get(
                    "evidenceHealth",
                    {
                        "state": "UNKNOWN",
                        "source": "CONSERVATIVE_FALLBACK",
                        "reasons": [],
                        "requiredDeviceCodes": [],
                    },
                ),
                "activePlan": active_plan,
                "anomalies": [],
                "integration": {
                    "dataPlane": "AVAILABLE" if self.telemetry is not None else "UNAVAILABLE",
                    "agents": "AVAILABLE" if self.workflow is not None else "UNAVAILABLE",
                },
                "plans": copy.deepcopy(list(self.plans.values())),
                "inspectionTasks": copy.deepcopy(list(self.tasks.values())),
            }

    def get_plan(self, revision_id: str) -> dict[str, Any]:
        with self._lock:
            if revision_id not in self.plans:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            return copy.deepcopy(self.plans[revision_id])

    def plan_status(self, revision_id: str) -> str:
        with self._lock:
            plan = self.plans.get(revision_id)
            return str(plan.get("status")) if plan is not None else "UNAVAILABLE"

    def decide_approval(
        self,
        *,
        plan_revision_id: str,
        revision_hash: str,
        decision: str,
        comment: str | None,
        operator: OperatorIdentity,
    ) -> dict[str, Any]:
        with self._lock:
            plan = self.plans.get(plan_revision_id)
            if plan is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            if plan.get("revisionHash") != revision_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="revision hash mismatch"
                )
            if plan.get("status") != "PROPOSED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="only the current PROPOSED revision can be decided",
                )
            if decision == "APPROVE" and any(
                challenge.get("blocking") is True
                and challenge.get("status") not in {"RESOLVED", "CLOSED"}
                for challenge in plan.get("challenges", [])
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="plan has an open blocking challenge",
                )
            approval_id = f"approval_{uuid.uuid4().hex[:10]}"
            now = utc_now()
            approval = {
                "approvalId": approval_id,
                "planRevisionId": plan_revision_id,
                "revisionHash": revision_hash,
                "approver": operator.actor,
                "decision": decision,
                "timestamp": now.isoformat(),
                "expiresAt": (now + timedelta(minutes=30)).isoformat(),
                "comment": comment,
            }
            self.approvals[approval_id] = approval
            plan["status"] = "APPROVED" if decision == "APPROVE" else "REJECTED"
            self._audit(
                f"approval.{decision.lower()}",
                operator,
                {"approvalId": approval_id, "planRevisionId": plan_revision_id},
            )
            workflow = self.workflow
            plan_snapshot = copy.deepcopy(plan)
        if decision == "APPROVE" and workflow is not None:
            on_approved = getattr(workflow, "on_approved", None)
            if callable(on_approved):
                try:
                    on_approved(plan_snapshot, dict(approval))
                except Exception:
                    with self._lock:
                        self._system_audit(
                            "approval.execution_failed", {"planRevisionId": plan_revision_id}
                        )
        return approval

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(list(self.tasks.values()))

    def transition_task(
        self,
        task_id: str,
        target: str,
        operator: OperatorIdentity,
    ) -> dict[str, Any]:
        with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
            current = str(task.get("status", "UNREAD")).upper()
            allowed_from = {
                "ACKNOWLEDGED": {"UNREAD", "CREATED"},
                "RESOLVED": {"ACKNOWLEDGED"},
            }
            if current != target and current not in allowed_from[target]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"task cannot transition from {current} to {target}",
                )
            task["status"] = target
            task["updatedAt"] = utc_now().isoformat()
            self._audit(f"task.{target.lower()}", operator, {"taskId": task_id})
            return copy.deepcopy(task)

    def get_timeline(self, trace_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if trace_id not in self.timeline:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trace not found")
            return copy.deepcopy(self.timeline[trace_id])

    def get_explanation(self, decision_id: str) -> dict[str, Any]:
        with self._lock:
            if decision_id not in self.explanations:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="decision not found"
                )
            return copy.deepcopy(self.explanations[decision_id])

    def configure_simulator(
        self,
        adapter: SimulatorAdapter,
        idempotency: IdempotencyStore,
    ) -> None:
        with self._lock:
            self.simulator_control = SimulatorControlGate(adapter, idempotency)

    def configure_workflow(self, workflow: FarmWorkflowPort) -> None:
        with self._lock:
            self.workflow = workflow

    def configure_telemetry(self, telemetry: TelemetryPort) -> None:
        with self._lock:
            self.telemetry = telemetry

    def upsert_plan(self, plan: dict[str, Any]) -> None:
        with self._lock:
            self.plans[plan["planRevisionId"]] = plan

    def set_active_plan(self, plan_lineage_id: str, plan_revision_id: str) -> None:
        with self._lock:
            self.active_plans[plan_lineage_id] = plan_revision_id

    def set_plan_status(self, plan_revision_id: str, plan_status: str) -> None:
        with self._lock:
            plan = self.plans.get(plan_revision_id)
            if plan is not None:
                plan["status"] = plan_status

    def record_verification(self, plan_revision_id: str, verification: dict[str, Any]) -> None:
        with self._lock:
            plan = self.plans.get(plan_revision_id)
            if plan is not None:
                plan.setdefault("verifications", []).append(verification)

    def append_timeline_event(self, trace_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            self.timeline.setdefault(trace_id, []).append(event)

    def record_explanation(self, decision_id: str, nodes: list[dict[str, Any]]) -> None:
        with self._lock:
            self.explanations[decision_id] = {"decisionId": decision_id, "nodes": nodes}

    def add_task(self, task: dict[str, Any]) -> None:
        with self._lock:
            self.tasks[task["id"]] = task

    def scope_verdicts(self) -> list[dict[str, Any]]:
        with self._lock:
            return self.telemetry.scope_verdicts() if self.telemetry is not None else []

    def submit_sim_command(
        self,
        operation: str,
        command_id: str,
        params: dict[str, object],
        operator: OperatorIdentity,
    ) -> dict[str, Any]:
        with self._lock:
            control = self.simulator_control
            if control is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="simulator integration unavailable",
                )
            self._audit(
                "sim.command.requested",
                operator,
                {"operation": operation, "commandId": command_id},
            )
        try:
            result = control.execute(
                operation=operation,
                command_id=command_id,
                params=params,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except SimulatorCommandInProgress as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except Exception as error:
            with self._lock:
                self._audit(
                    "sim.command.uncertain",
                    operator,
                    {"operation": operation, "commandId": command_id},
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="simulator command outcome is uncertain; do not retry with a new command id",
            ) from error
        with self._lock:
            self._audit(
                "sim.command.completed",
                operator,
                {
                    "operation": operation,
                    "commandId": command_id,
                    "deliveryStatus": result.delivery_status,
                },
            )
        return {"deliveryStatus": result.delivery_status, **dict(result.data)}

    def expire_stale_plans(self, now: datetime | None = None) -> int:
        """Continuously enforce approval/proposal TTL, not only during restart."""

        now = now or utc_now()
        expired = 0
        with self._lock:
            for approval in self.approvals.values():
                if approval.get("revokedAt") is not None:
                    continue
                expires_at = _parse_datetime(approval.get("expiresAt"))
                if expires_at is not None and expires_at > now:
                    continue
                approval["revokedAt"] = now.isoformat()
                revision_id = str(approval.get("planRevisionId", ""))
                plan = self.plans.get(revision_id)
                if (
                    plan is not None
                    and plan.get("revisionHash") == approval.get("revisionHash")
                    and plan.get("status") in {"APPROVED", "EXECUTING"}
                ):
                    plan["status"] = "EXPIRED"
                    expired += 1
                    self._system_audit("approval.expired", {"planRevisionId": revision_id})

            for revision_id, plan in self.plans.items():
                if plan.get("status") != "PROPOSED":
                    continue
                deadline = _parse_datetime(plan.get("proposalExpiresAt"))
                created_at = _parse_datetime(plan.get("createdAt"))
                deadline = deadline or (
                    created_at + timedelta(minutes=30) if created_at is not None else None
                )
                if deadline is None or deadline <= now:
                    plan["status"] = "EXPIRED"
                    expired += 1
                    self._system_audit("proposal.expired", {"planRevisionId": revision_id})
        return expired

    def health(self) -> dict[str, Any]:
        snapshot = self.telemetry.health_snapshot() if self.telemetry is not None else None
        return {
            "status": (snapshot or {}).get("status", "degraded"),
            "uptimeSeconds": round(time.monotonic() - self.started_at, 3),
            "batchPeriodSeconds": (snapshot or {}).get("batchPeriodSeconds"),
            "lateRatio": (snapshot or {}).get("lateRatio"),
            "clockSkewSeconds": (snapshot or {}).get("clockSkewSeconds"),
            "outboxDepth": (snapshot or {}).get("outboxDepth"),
            "missingDevices": (snapshot or {}).get("missingDevices", []),
            "reasons": (snapshot or {}).get(
                "reasons", [] if snapshot is not None else ["data plane not wired"]
            ),
            "integrations": {
                "dataPlane": "ready" if self.telemetry is not None else "pending M1",
                "trust": "ready" if self.telemetry is not None else "pending M2",
                "agents": "ready" if self.workflow is not None else "pending M3",
            },
        }

    def _audit(self, event: str, operator: OperatorIdentity, details: dict[str, Any]) -> None:
        self.audit.append(
            {
                "event": event,
                "actor": operator.actor,
                "tokenId": operator.token_id,
                "timestamp": utc_now().isoformat(),
                "details": details,
            }
        )

    def _system_audit(self, event: str, details: dict[str, Any]) -> None:
        self.audit.append(
            {
                "event": event,
                "actor": "system:runtime",
                "tokenId": "system",
                "timestamp": utc_now().isoformat(),
                "details": details,
            }
        )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


service = FarmOpsService()
