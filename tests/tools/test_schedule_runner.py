from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from schedule.claim import InMemoryScheduleRepository, ScheduleConflict
from schedule.models import Schedule, ScheduleStatus
from schedule.runner import NoActuation, ScheduleRunner
from verify.ledger import InMemoryWaterLedger, Reconciliation

pytestmark = pytest.mark.tools


def make_schedule(schedule_id: str, *, status: ScheduleStatus = ScheduleStatus.PENDING) -> Schedule:
    now = datetime.now(UTC)
    return Schedule(
        schedule_id=schedule_id,
        plan_revision_id="PLAN-1-V1",
        pump_id="PUMP_01",
        start_at=now,
        end_at=now + timedelta(minutes=10),
        status=status,
        planned_drawdown_pct=5.0,
        planned_pump_minutes=10.0,
    )


def test_two_concurrent_claims_exactly_one_wins() -> None:
    repository = InMemoryScheduleRepository()
    repository.add(make_schedule("schedule-1"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda worker: repository.try_claim("schedule-1", worker), ["a", "b"])
        )
    assert sum(results) == 1
    assert repository.get("schedule-1").status is ScheduleStatus.RUNNING


def test_running_pump_constraint_rejects_second_schedule() -> None:
    repository = InMemoryScheduleRepository()
    repository.add(make_schedule("schedule-1", status=ScheduleStatus.RUNNING))
    with pytest.raises(ScheduleConflict):
        repository.add(make_schedule("schedule-2", status=ScheduleStatus.RUNNING))


def test_past_grace_is_missed_without_catch_up() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-1")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(schedule.start_at + timedelta(minutes=3))
    assert schedule.status is ScheduleStatus.MISSED


def test_low_tank_never_enters_running() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-1")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 19.9,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        safe_reserve_pct=20.0,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_pending_schedule_waits_until_plan_is_approved() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-1")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "PROPOSED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.PENDING


def test_expired_plan_cancels_pending_schedule() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-1")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "EXPIRED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_schedule_is_cancelled_when_execution_authorization_expires() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-expired-approval")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: False,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_actuator_start_failure_releases_running_pump_lock() -> None:
    class FailingActuator:
        def start(self, schedule):
            del schedule
            raise RuntimeError("sim unavailable")

        def stop(self, schedule):
            del schedule

    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-1")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=FailingActuator(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.FAILED
    repository.add(make_schedule("schedule-2", status=ScheduleStatus.RUNNING))


@pytest.mark.parametrize("level", [float("nan"), float("inf"), -1.0, 101.0])
def test_invalid_tank_evidence_never_enters_running(level) -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-invalid-tank")
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: level,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_closing_schedule_retries_verification_without_killing_runner() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-closing", status=ScheduleStatus.RUNNING)
    schedule.start_at -= timedelta(minutes=11)
    schedule.end_at -= timedelta(minutes=10)
    repository.add(schedule)
    results = iter([RuntimeError("trust unavailable"), "PASS"])
    ledger = InMemoryWaterLedger()

    def verify(_schedule):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=verify,
        record_ledger=ledger.record_schedule,
    )
    now = datetime.now(UTC)
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CLOSING
    runner.tick(now + timedelta(seconds=5))
    assert schedule.status is ScheduleStatus.DONE
    assert len(ledger.entries) == 1
    assert ledger.entries[0].action_id == "schedule-closing"
    assert ledger.entries[0].reconciliation is Reconciliation.INCONCLUSIVE


def test_ledger_write_is_required_before_terminal_transition() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-ledger", status=ScheduleStatus.RUNNING)
    schedule.start_at -= timedelta(minutes=11)
    schedule.end_at -= timedelta(minutes=10)
    repository.add(schedule)
    attempts = 0

    def record(_schedule, _result):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("database unavailable")

    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "INCONCLUSIVE",
        record_ledger=record,
    )
    now = datetime.now(UTC)
    runner.tick(now)
    assert schedule.status is ScheduleStatus.CLOSING
    runner.tick(now + timedelta(seconds=5))
    assert schedule.status is ScheduleStatus.DONE
    assert attempts == 2


def test_planned_drawdown_over_budget_is_cancelled() -> None:
    repository = InMemoryScheduleRepository()
    schedule = make_schedule("schedule-budget")
    schedule.planned_drawdown_pct = 8.0
    repository.add(schedule)
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 6.5,
    )
    runner.tick(schedule.start_at)
    assert schedule.status is ScheduleStatus.CANCELLED


def test_verification_failure_at_deadline_becomes_terminal_inconclusive() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    schedule = Schedule(
        "schedule-deadline",
        "PLAN-1-V1",
        "PUMP_01",
        now - timedelta(minutes=30),
        now - timedelta(minutes=20),
        ScheduleStatus.RUNNING,
        planned_drawdown_pct=5.0,
        planned_pump_minutes=10.0,
    )
    repository.add(schedule)
    ledger = InMemoryWaterLedger()
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=lambda _: "APPROVED",
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: (_ for _ in ()).throw(RuntimeError("trust unavailable")),
        record_ledger=ledger.record_schedule,
    )
    runner.tick(now)
    assert schedule.status is ScheduleStatus.FAILED
    assert schedule.verification_result == "INCONCLUSIVE"
    assert len(ledger.entries) == 1


def test_one_bad_plan_state_does_not_block_other_schedules() -> None:
    repository = InMemoryScheduleRepository()
    bad = make_schedule("schedule-bad")
    good = make_schedule("schedule-good")
    good.pump_id = "PUMP_02"
    repository.add(bad)
    repository.add(good)

    def plan_status(revision_id):
        if revision_id == bad.plan_revision_id and bad.schedule_id == "schedule-bad":
            # Distinguish by changing the good row's revision below.
            raise RuntimeError("state unavailable")
        return "APPROVED"

    good.plan_revision_id = "PLAN-2-V1"
    runner = ScheduleRunner(
        repository=repository,
        worker_id="worker-1",
        actuator=NoActuation(),
        plan_status=plan_status,
        authorize_schedule=lambda _: True,
        tank_level=lambda: 60.0,
        verify_outcome=lambda _: "PASS",
        record_ledger=lambda _schedule, _result: None,
        available_drawdown_budget=lambda: 20.0,
    )
    runner.tick(max(bad.start_at, good.start_at))
    assert bad.status is ScheduleStatus.PENDING
    assert good.status is ScheduleStatus.RUNNING
