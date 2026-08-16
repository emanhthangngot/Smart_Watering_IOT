"""Permission-gated irrigation tool façade.

No caller receives the raw adapter.  This is the only module that invokes it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from contracts import ToolPermission

from .downgrade import downgrade_sequence
from .idempotency import ClaimState, IdempotencyStore, idempotency_key
from .permission import PermissionDecision, ToolContext, ToolStateStore, evaluate_permission


class ToolAdapter(Protocol):
    def call(self, tool: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ToolExecution:
    requested_tool: str
    executed_tool: str | None
    status: str
    downgrade_hops: int
    idempotency_key: str | None
    data: Mapping[str, Any] | None
    decision: PermissionDecision
    attempts: tuple[tuple[str, PermissionDecision], ...] = ()


class IrrigationToolLayer:
    def __init__(
        self,
        *,
        permissions: Mapping[str, ToolPermission],
        idempotency: IdempotencyStore,
        adapter: ToolAdapter,
        state_store: ToolStateStore,
    ) -> None:
        self._permissions = dict(permissions)
        self._idempotency = idempotency
        self._adapter = adapter
        self._state_store = state_store

    def authorize_existing(
        self,
        tool: str,
        plan_revision_id: str,
    ) -> PermissionDecision:
        """Re-authorize a persisted action immediately before execution."""

        context = self._state_store.get_context(plan_revision_id)
        if context is None:
            return PermissionDecision(
                False,
                "PLAN_STATE_UNAVAILABLE",
                "authoritative plan state is unavailable",
            )
        permission = self._permissions.get(tool)
        if permission is None:
            return PermissionDecision(False, "TOOL_UNKNOWN", "tool policy is missing")
        decision = evaluate_permission(permission, context)
        if not decision.allowed:
            return decision
        if any(not self._state_store.evidence_exists(ref) for ref in context.evidence_refs):
            return PermissionDecision(
                False,
                "EVIDENCE_UNGROUNDED",
                "one or more evidence references do not exist in the authoritative store",
            )
        return decision

    def execute(
        self,
        requested_tool: str,
        params: Mapping[str, Any],
        plan_revision_id: str,
    ) -> ToolExecution:
        context = self._state_store.get_context(plan_revision_id)
        if context is None:
            decision = PermissionDecision(
                False,
                "PLAN_STATE_UNAVAILABLE",
                "authoritative plan state is unavailable",
            )
            return ToolExecution(
                requested_tool=requested_tool,
                executed_tool=None,
                status="DENIED",
                downgrade_hops=0,
                idempotency_key=None,
                data=None,
                decision=decision,
                attempts=((requested_tool, decision),),
            )

        last_decision = PermissionDecision(False, "TOOL_UNKNOWN", "tool policy is missing")
        attempts: list[tuple[str, PermissionDecision]] = []
        for hops, candidate in enumerate(downgrade_sequence(requested_tool)):
            permission = self._permissions.get(candidate)
            if permission is None:
                last_decision = PermissionDecision(
                    False, "TOOL_UNKNOWN", f"no policy for {candidate}"
                )
                attempts.append((candidate, last_decision))
                continue
            last_decision = evaluate_permission(permission, context)
            if not last_decision.allowed:
                attempts.append((candidate, last_decision))
                continue

            missing_refs = [
                ref for ref in context.evidence_refs if not self._state_store.evidence_exists(ref)
            ]
            if missing_refs:
                last_decision = PermissionDecision(
                    False,
                    "EVIDENCE_UNGROUNDED",
                    "one or more evidence references do not exist in the authoritative store",
                )
                attempts.append((candidate, last_decision))
                continue

            candidate_params = _candidate_params(
                requested_tool=requested_tool,
                candidate=candidate,
                original=params,
                context=context,
                prior_attempts=attempts,
            )
            validation = _validate_params(candidate, candidate_params)
            if not validation.allowed:
                last_decision = validation
                attempts.append((candidate, last_decision))
                continue
            attempts.append((candidate, last_decision))

            key = idempotency_key(context.plan_revision_id, candidate, candidate_params)
            claim = self._idempotency.claim(key)
            if claim.state is ClaimState.COMPLETED:
                return ToolExecution(
                    requested_tool=requested_tool,
                    executed_tool=candidate,
                    status="DUPLICATE_REPLAY",
                    downgrade_hops=hops,
                    idempotency_key=key,
                    data=claim.result,
                    decision=last_decision,
                    attempts=tuple(attempts),
                )
            if claim.state is ClaimState.IN_PROGRESS:
                return ToolExecution(
                    requested_tool=requested_tool,
                    executed_tool=candidate,
                    status="IN_PROGRESS",
                    downgrade_hops=hops,
                    idempotency_key=key,
                    data=None,
                    decision=last_decision,
                    attempts=tuple(attempts),
                )
            try:
                result = dict(self._adapter.call(candidate, candidate_params))
            except Exception:
                # The adapter may have committed the side effect before its
                # response was lost. Keep the claim IN_PROGRESS so a blind
                # retry cannot create a duplicate; recovery/read-back must
                # reconcile it explicitly.
                raise
            self._idempotency.complete(key, result)
            return ToolExecution(
                requested_tool=requested_tool,
                executed_tool=candidate,
                status="EXECUTED",
                downgrade_hops=hops,
                idempotency_key=key,
                data=result,
                decision=last_decision,
                attempts=tuple(attempts),
            )

        return ToolExecution(
            requested_tool=requested_tool,
            executed_tool=None,
            status="DENIED",
            downgrade_hops=max(0, len(downgrade_sequence(requested_tool)) - 1),
            idempotency_key=None,
            data=None,
            decision=last_decision,
            attempts=tuple(attempts),
        )


def _candidate_params(
    *,
    requested_tool: str,
    candidate: str,
    original: Mapping[str, Any],
    context: ToolContext,
    prior_attempts: list[tuple[str, PermissionDecision]],
) -> dict[str, Any]:
    if candidate == requested_tool:
        return dict(original)
    reason = prior_attempts[-1][1].reason if prior_attempts else "safer action required"
    if candidate == "propose_irrigation_plan":
        return {
            "requestedTool": requested_tool,
            "requestedParams": dict(original),
            "reason": reason,
            "evidenceRefs": list(context.evidence_refs),
        }
    if candidate == "create_inspection_task":
        device = original.get("device") or original.get("pump_id") or original.get("pumpId")
        return {
            "device": device or "FARM",
            "reason": reason,
            "evidenceRefs": list(context.evidence_refs),
            "priority": "HIGH",
            "check": "Verify device state and blocking evidence before replanning.",
        }
    return dict(original)


def _validate_params(tool: str, params: Mapping[str, Any]) -> PermissionDecision:
    if not params:
        return PermissionDecision(False, "PARAMS_INVALID", "tool parameters cannot be empty")
    if not _values_are_safe(params):
        return PermissionDecision(
            False,
            "PARAMS_INVALID",
            "tool parameters contain non-finite or negative operational values",
        )
    if tool == "create_irrigation_schedule":
        pump = params.get("pump_id") or params.get("pumpId")
        if not isinstance(pump, str) or not pump.strip():
            return PermissionDecision(False, "PARAMS_INVALID", "a non-empty pump id is required")
        drawdown = params.get("planned_drawdown_pct", params.get("plannedDrawdownPct"))
        minutes = params.get(
            "planned_pump_minutes",
            params.get("plannedPumpMinutes", params.get("minutes")),
        )
        if not isinstance(drawdown, (int, float)) or isinstance(drawdown, bool) or drawdown <= 0:
            return PermissionDecision(
                False,
                "PARAMS_INVALID",
                "planned_drawdown_pct must be positive",
            )
        if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or minutes <= 0:
            return PermissionDecision(
                False,
                "PARAMS_INVALID",
                "planned pump minutes must be positive",
            )
    if tool == "create_inspection_task":
        required = ("device", "reason", "evidenceRefs", "priority", "check")
        if any(not params.get(key) for key in required):
            return PermissionDecision(
                False,
                "PARAMS_INVALID",
                "inspection task requires device, reason, evidence, priority and check",
            )
    return PermissionDecision(True, "PARAMS_VALID", "tool parameters are valid")


def _values_are_safe(value: Any, key: str = "") -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return False
        lowered = key.lower()
        if any(marker in lowered for marker in ("minute", "duration", "drawdown")):
            return value >= 0
        return True
    if isinstance(value, Mapping):
        return all(_values_are_safe(item, str(item_key)) for item_key, item in value.items())
    if isinstance(value, (list, tuple)):
        return all(_values_are_safe(item, key) for item in value)
    return False


def default_permissions() -> dict[str, ToolPermission]:
    formula = "sha1(planRevisionId | tool | canonical(params))"
    return {
        "create_irrigation_schedule": ToolPermission(
            tool="create_irrigation_schedule",
            allowed_plan_statuses=["APPROVED"],
            min_tier="PROPOSE",
            approval_required=True,
            idempotency_key_formula=formula,
        ),
        "propose_irrigation_plan": ToolPermission(
            tool="propose_irrigation_plan",
            allowed_plan_statuses=["DRAFT", "PROPOSED", "APPROVED"],
            min_tier="PROPOSE",
            approval_required=False,
            idempotency_key_formula=formula,
        ),
        "create_inspection_task": ToolPermission(
            tool="create_inspection_task",
            allowed_plan_statuses=[
                "DRAFT",
                "PROPOSED",
                "APPROVED",
                "EXECUTING",
                "SUSPENDED",
                "NEEDS_REPLAN",
                "EXPIRED",
                "REJECTED",
                "CHALLENGED",
                "VERIFIED",
                "COMPLETED",
            ],
            min_tier="INVESTIGATE",
            approval_required=False,
            idempotency_key_formula=formula,
        ),
    }


class InMemoryToolAdapter:
    """Observable local adapter used by tests and the API scaffold."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        copied = dict(params)
        self.calls.append((tool, copied))
        return {"id": f"{tool}-{len(self.calls)}", "status": "CREATED", "params": copied}
