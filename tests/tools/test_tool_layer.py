from datetime import UTC, datetime, timedelta

import pytest

from contracts import Approval
from tools.idempotency import InMemoryIdempotencyStore, idempotency_key
from tools.irrigation import InMemoryToolAdapter, IrrigationToolLayer, default_permissions
from tools.permission import InMemoryToolStateStore, ToolContext

pytestmark = pytest.mark.tools


def approval(revision_hash: str = "hash-v1") -> Approval:
    now = datetime.now(UTC)
    return Approval(
        approval_id="approval-1",
        plan_revision_id="PLAN-1-V1",
        revision_hash=revision_hash,
        approver="operator",
        decision="APPROVE",
        timestamp=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat(),
    )


def context(**overrides) -> ToolContext:
    values = {
        "plan_revision_id": "PLAN-1-V1",
        "revision_hash": "hash-v1",
        "current_revision_hash": "hash-v1",
        "plan_status": "APPROVED",
        "tier": "PROPOSE",
        "evidence_refs": ("r_a3f9c1#soil_moisture",),
        "approval": approval(),
    }
    values.update(overrides)
    return ToolContext(**values)


def layer(tool_context=None, *, ground_evidence=True):
    tool_context = tool_context or context()
    adapter = InMemoryToolAdapter()
    state_store = InMemoryToolStateStore()
    state_store.put_context(tool_context)
    if ground_evidence:
        state_store.add_evidence(*tool_context.evidence_refs)
    tool_layer = IrrigationToolLayer(
        permissions=default_permissions(),
        idempotency=InMemoryIdempotencyStore(),
        adapter=adapter,
        state_store=state_store,
    )
    return tool_layer, adapter, state_store


def test_stale_revision_hash_denies_without_side_effect() -> None:
    tool_layer, adapter, _ = layer(context(current_revision_hash="hash-v2"))
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01", "minutes": 10},
        "PLAN-1-V1",
    )
    assert result.status == "DENIED"
    assert adapter.calls == []


def test_duplicate_call_replays_one_result_and_one_side_effect() -> None:
    tool_layer, adapter, _ = layer()
    params = {
        "pump_id": "PUMP_01",
        "minutes": 10,
        "planned_drawdown_pct": 5.0,
    }
    first = tool_layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    second = tool_layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    assert first.status == "EXECUTED"
    assert second.status == "DUPLICATE_REPLAY"
    assert first.data == second.data
    assert len(adapter.calls) == 1


def test_refusal_downgrades_at_most_two_hops() -> None:
    tool_layer, adapter, _ = layer(
        context(plan_status="SUSPENDED", tier="INVESTIGATE", approval=None)
    )
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"device": "SOIL_01", "reason": "required evidence offline"},
        "PLAN-1-V1",
    )
    assert result.status == "EXECUTED"
    assert result.executed_tool == "create_inspection_task"
    assert result.downgrade_hops == 2
    assert adapter.calls[0][0] == "create_inspection_task"


def test_idempotency_key_is_canonical() -> None:
    left = idempotency_key("PLAN-1-V1", "tool", {"b": 2, "a": 1})
    right = idempotency_key("PLAN-1-V1", "tool", {"a": 1, "b": 2})
    assert left == right


def test_ambiguous_adapter_failure_is_not_blindly_retried() -> None:
    class CommitThenFailAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def call(self, tool, params):
            del tool, params
            self.calls += 1
            raise TimeoutError("response lost after possible commit")

    adapter = CommitThenFailAdapter()
    state_store = InMemoryToolStateStore()
    state_store.put_context(context())
    state_store.add_evidence(*context().evidence_refs)
    tool_layer = IrrigationToolLayer(
        permissions=default_permissions(),
        idempotency=InMemoryIdempotencyStore(),
        adapter=adapter,
        state_store=state_store,
    )
    params = {
        "pump_id": "PUMP_01",
        "minutes": 10,
        "planned_drawdown_pct": 5.0,
    }
    with pytest.raises(TimeoutError):
        tool_layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    retry = tool_layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    assert retry.status == "IN_PROGRESS"
    assert adapter.calls == 1


def test_malformed_approval_expiry_fails_closed() -> None:
    invalid = approval()
    invalid.expires_at = "not-a-timestamp"
    tool_layer, adapter, _ = layer(context(approval=invalid))
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01"},
        "PLAN-1-V1",
    )
    assert result.executed_tool == "propose_irrigation_plan"
    assert all(tool != "create_irrigation_schedule" for tool, _ in adapter.calls)


def test_caller_cannot_supply_fabricated_plan_state() -> None:
    tool_layer, adapter, _ = layer()
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01", "minutes": 10},
        "PLAN-DOES-NOT-EXIST",
    )
    assert result.decision.code == "PLAN_STATE_UNAVAILABLE"
    assert adapter.calls == []


def test_ungrounded_evidence_denies_every_side_effect() -> None:
    tool_layer, adapter, _ = layer(ground_evidence=False)
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01", "minutes": 10},
        "PLAN-1-V1",
    )
    assert result.status == "DENIED"
    assert {attempt.code for _, attempt in result.attempts} == {"EVIDENCE_UNGROUNDED"}
    assert adapter.calls == []


def test_downgraded_inspection_receives_complete_task_contract() -> None:
    tool_layer, adapter, _ = layer(
        context(plan_status="SUSPENDED", tier="INVESTIGATE", approval=None)
    )
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01", "minutes": -1},
        "PLAN-1-V1",
    )
    assert result.executed_tool == "create_inspection_task"
    _, params = adapter.calls[-1]
    assert set(("device", "reason", "evidenceRefs", "priority", "check")) <= params.keys()


def test_rejected_plan_can_still_downgrade_to_safe_inspection() -> None:
    tool_layer, adapter, _ = layer(
        context(plan_status="REJECTED", tier="INVESTIGATE", approval=None)
    )
    result = tool_layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01", "minutes": 10, "planned_drawdown_pct": 5.0},
        "PLAN-1-V1",
    )
    assert result.executed_tool == "create_inspection_task"
    assert adapter.calls[-1][0] == "create_inspection_task"


def test_persisted_schedule_is_reauthorized_before_execution() -> None:
    expired = approval()
    expired.expires_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    tool_layer, _, _ = layer(context(approval=expired))
    decision = tool_layer.authorize_existing("create_irrigation_schedule", "PLAN-1-V1")
    assert decision.allowed is False
    assert decision.code == "APPROVAL_EXPIRED"
