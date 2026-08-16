"""INV-2: active planned drawdown cannot consume the safe reserve."""

from datetime import UTC, datetime, timedelta

import pytest

from schedule import InMemoryScheduleRepository, Schedule, ScheduleRunner, ScheduleStatus
from schedule.runner import NoActuation
from verify.ledger import available_drawdown_budget

pytestmark = pytest.mark.invariants


def test_committed_drawdown_is_subtracted_from_available_budget() -> None:
    assert available_drawdown_budget(59.8, 20.0, 6.5) == pytest.approx(33.3)
    assert available_drawdown_budget(20.0, 20.0, 0.0) == 0.0
    assert available_drawdown_budget(19.0, 20.0, 0.0) == 0.0


def test_schedule_cannot_claim_more_than_remaining_daily_budget() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    schedule = Schedule(
        "s-budget",
        "p1",
        "PUMP_01",
        now,
        now + timedelta(minutes=5),
        planned_drawdown_pct=8.0,
    )
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 59.8,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 6.5,
    )
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CANCELLED
