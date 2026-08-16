"""INV-6: side effects require the current revision and valid approval."""

from datetime import UTC, datetime, timedelta

import pytest

from contracts import Approval
from schedule import InMemoryScheduleRepository, Schedule, ScheduleRunner, ScheduleStatus
from tools.idempotency import InMemoryIdempotencyStore
from tools.irrigation import InMemoryToolAdapter, IrrigationToolLayer, default_permissions
from tools.permission import InMemoryToolStateStore, ToolContext

pytestmark = pytest.mark.invariants


def test_revision_mismatch_never_reaches_adapter() -> None:
    now = datetime.now(UTC)
    adapter = InMemoryToolAdapter()
    approval = Approval(
        "a1",
        "PLAN-1-V1",
        "old-hash",
        "operator",
        "APPROVE",
        now.isoformat(),
        (now + timedelta(minutes=30)).isoformat(),
    )
    state_store = InMemoryToolStateStore()
    context = ToolContext(
        plan_revision_id="PLAN-1-V1",
        revision_hash="old-hash",
        current_revision_hash="new-hash",
        plan_status="APPROVED",
        tier="AUTO",
        evidence_refs=("r_123456#level",),
        approval=approval,
    )
    state_store.put_context(context)
    state_store.add_evidence(*context.evidence_refs)
    layer = IrrigationToolLayer(
        permissions=default_permissions(),
        idempotency=InMemoryIdempotencyStore(),
        adapter=adapter,
        state_store=state_store,
    )
    result = layer.execute(
        "create_irrigation_schedule",
        {"pump_id": "PUMP_01"},
        "PLAN-1-V1",
    )
    assert result.status == "DENIED"
    assert adapter.calls == []


def test_persisted_schedule_is_reauthorized_before_actuation() -> None:
    class Actuator:
        def __init__(self) -> None:
            self.calls = []

        def start(self, schedule):
            self.calls.append(("start", schedule.schedule_id))

        def stop(self, schedule):
            self.calls.append(("stop", schedule.schedule_id))

    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    schedule = Schedule(
        "schedule-1",
        "PLAN-1-V1",
        "PUMP_01",
        now,
        now + timedelta(minutes=10),
        planned_drawdown_pct=5.0,
        planned_pump_minutes=10.0,
    )
    repository.add(schedule)
    actuator = Actuator()
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker",
        actuator=actuator,
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: False,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CANCELLED
    assert actuator.calls == []
