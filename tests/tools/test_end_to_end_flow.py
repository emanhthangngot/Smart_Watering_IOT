from datetime import UTC, datetime, timedelta

import pytest

from contracts import Approval
from schedule import InMemoryScheduleRepository, Schedule, ScheduleRunner, ScheduleStatus
from schedule.runner import NoActuation
from tools.idempotency import InMemoryIdempotencyStore
from tools.irrigation import IrrigationToolLayer, default_permissions
from tools.permission import InMemoryToolStateStore, ToolContext
from verify.action import verify_action
from verify.ledger import InMemoryWaterLedger, Reconciliation
from verify.outcome import verify_outcome

pytestmark = pytest.mark.tools


def test_approved_tool_to_schedule_to_outcome_to_ledger_flow() -> None:
    now = datetime.now(UTC)
    end = now + timedelta(minutes=10)
    repository = InMemoryScheduleRepository()

    class ScheduleAdapter:
        calls = 0

        def call(self, tool, params):
            assert tool == "create_irrigation_schedule"
            self.calls += 1
            schedule = Schedule(
                schedule_id="schedule-e2e",
                plan_revision_id="PLAN-1-V1",
                pump_id=params["pump_id"],
                start_at=datetime.fromisoformat(params["start_at"]),
                end_at=datetime.fromisoformat(params["end_at"]),
                planned_drawdown_pct=params["planned_drawdown_pct"],
                planned_pump_minutes=params["planned_pump_minutes"],
            )
            repository.add(schedule)
            return {"id": schedule.schedule_id, "status": "PENDING", "params": dict(params)}

    evidence_ref = "r_tank#level"
    approval = Approval(
        "approval-1",
        "PLAN-1-V1",
        "hash-v1",
        "operator",
        "APPROVE",
        now.isoformat(),
        (now + timedelta(minutes=30)).isoformat(),
    )
    state_store = InMemoryToolStateStore()
    state_store.put_context(
        ToolContext(
            plan_revision_id="PLAN-1-V1",
            revision_hash="hash-v1",
            current_revision_hash="hash-v1",
            plan_status="APPROVED",
            tier="PROPOSE",
            evidence_refs=(evidence_ref,),
            approval=approval,
        )
    )
    state_store.add_evidence(evidence_ref)
    adapter = ScheduleAdapter()
    layer = IrrigationToolLayer(
        permissions=default_permissions(),
        idempotency=InMemoryIdempotencyStore(),
        adapter=adapter,
        state_store=state_store,
    )
    params = {
        "pump_id": "PUMP_01",
        "start_at": now.isoformat(),
        "end_at": end.isoformat(),
        "planned_drawdown_pct": 5.0,
        "planned_pump_minutes": 10.0,
    }
    created = layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    duplicate = layer.execute("create_irrigation_schedule", params, "PLAN-1-V1")
    assert created.status == "EXECUTED"
    assert duplicate.status == "DUPLICATE_REPLAY"
    assert adapter.calls == 1

    action = verify_action(
        expected_id="schedule-e2e",
        expected_status="PENDING",
        expected_params=params,
        post_result=created.data or {},
        read_back={"id": "schedule-e2e", "status": "PENDING", "params": params},
        window="immediate",
        evidence_refs=[evidence_ref],
    )
    assert action.result == "PASS"

    ledger = InMemoryWaterLedger()

    def observational_outcome(_schedule):
        return verify_outcome(
            actuation_target="none",
            pump_activity_observed=False,
            evidence_usable=True,
            expected_met=None,
            expected={"soil_delta": ">0"},
            observed={"pumpActivity": False},
            window="10m",
            evidence_refs=[evidence_ref],
        ).result

    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-e2e",
        actuator=NoActuation(),
        plan_status=lambda revision_id: state_store.get_context(revision_id).plan_status,
        authorize_schedule=lambda row: (
            layer.authorize_existing("create_irrigation_schedule", row.plan_revision_id).allowed
        ),
        tank_level=lambda: 60.0,
        verify_outcome=observational_outcome,
        record_ledger=ledger.record_schedule,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(now)
    schedule = repository.get("schedule-e2e")
    assert schedule is not None and schedule.status is ScheduleStatus.RUNNING
    runner.tick(end)
    assert schedule.status is ScheduleStatus.DONE
    assert schedule.verification_result == "INCONCLUSIVE"
    assert len(ledger.entries) == 1
    assert ledger.entries[0].reconciliation is Reconciliation.INCONCLUSIVE
