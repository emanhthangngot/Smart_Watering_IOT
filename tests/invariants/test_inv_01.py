"""INV-1: no schedule RUNNING below the tank safe reserve."""

from datetime import UTC, datetime, timedelta

import pytest

from schedule import InMemoryScheduleRepository, Schedule, ScheduleRunner, ScheduleStatus
from schedule.runner import NoActuation

pytestmark = pytest.mark.invariants


def test_low_tank_schedule_is_cancelled_before_claim() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    schedule = Schedule("s1", "p1", "PUMP_01", now, now + timedelta(minutes=5))
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 19.9,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        safe_reserve_pct=20.0,
    )
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_non_finite_tank_level_is_never_treated_as_safe() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    schedule = Schedule("s-nan", "p1", "PUMP_01", now, now + timedelta(minutes=5))
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: float("nan"),
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
    )
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CANCELLED
