from datetime import UTC, datetime, timedelta

import pytest

from api.recovery import (
    RecoverableAction,
    RecoverableApproval,
    RecoverablePlan,
    action_terminal_deadline,
    recover,
)
from api.retention import RETENTION_BATCH_SIZE, run_retention
from schedule.claim import InMemoryScheduleRepository
from schedule.models import Schedule, ScheduleStatus

pytestmark = pytest.mark.tools


class FakeRecoveryPort:
    def __init__(self, now: datetime) -> None:
        self._plans = [RecoverablePlan("PLAN-1-V1", "EXECUTING")]
        self._approvals = [
            RecoverableApproval("approval-1", "PLAN-2-V1", now - timedelta(seconds=1))
        ]
        self._actions = [RecoverableAction("action-1", terminal=False, has_verification=False)]
        self.calls: list[tuple] = []
        self.verification_keys: set[str] = set()

    def plans(self):
        return self._plans

    def approvals(self):
        return self._approvals

    def actions(self):
        return self._actions

    def reattach_plan_monitor(self, plan_revision_id):
        self.calls.append(("reattach", plan_revision_id))

    def reevaluate_assumptions(self, plan_revision_id):
        self.calls.append(("reevaluate", plan_revision_id))

    def stop_recovered_schedule(self, schedule_id):
        self.calls.append(("stop", schedule_id))

    def expire_approval_and_plan(self, approval_id, plan_revision_id):
        self.calls.append(("expire", approval_id, plan_revision_id))

    def queue_verification(self, identifier, *, late, idempotency_key):
        if idempotency_key not in self.verification_keys:
            self.verification_keys.add(idempotency_key)
            self.calls.append(("verify", identifier, late, idempotency_key))
            return True
        return False

    def finalize_overdue_action_with_verification(self, action_id, *, reason):
        self.calls.append(("finalize", action_id, reason))


def test_restart_recovery_handles_all_nonterminal_cases() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    running = Schedule(
        schedule_id="schedule-1",
        plan_revision_id="PLAN-1-V1",
        pump_id="PUMP_01",
        start_at=now - timedelta(minutes=10),
        end_at=now - timedelta(minutes=5),
        status=ScheduleStatus.RUNNING,
    )
    pending = Schedule(
        schedule_id="schedule-2",
        plan_revision_id="PLAN-2-V1",
        pump_id="PUMP_02",
        start_at=now - timedelta(minutes=5),
        end_at=now + timedelta(minutes=5),
    )
    repository.add(running)
    repository.add(pending)
    port = FakeRecoveryPort(now)
    report = recover(repository, port, now=now)
    assert running.status is ScheduleStatus.CLOSING
    assert running.actuator_stopped is True
    assert running.late_verification is True
    assert pending.status is ScheduleStatus.MISSED
    assert report.schedules_closing == 1
    assert report.schedules_missed == 1
    assert report.plans_reattached == 1
    assert report.approvals_revoked == 1
    assert report.verifications_queued == 2
    assert port.calls.index(("stop", "schedule-1")) < next(
        index for index, call in enumerate(port.calls) if call[0:2] == ("verify", "schedule-1")
    )
    second = recover(repository, port, now=now)
    assert second.verifications_queued == 0
    assert len([call for call in port.calls if call[0] == "verify"]) == 2


def test_retention_rolls_up_then_deletes_in_bounded_batches() -> None:
    class RetentionPort:
        def __init__(self) -> None:
            self.calls = []
            self.counts = [RETENTION_BATCH_SIZE, 17]

        def rollup_before(self, cutoff):
            self.calls.append(("rollup", cutoff))

        def delete_sensor_batch(self, cutoff, limit):
            self.calls.append(("delete", cutoff, limit))
            return self.counts.pop(0)

    cutoff = datetime.now(UTC) - timedelta(days=7)
    port = RetentionPort()
    deleted = run_retention(port, cutoff)
    assert deleted == RETENTION_BATCH_SIZE + 17
    assert port.calls[0] == ("rollup", cutoff)
    assert port.calls[1:] == [
        ("delete", cutoff, RETENTION_BATCH_SIZE),
        ("delete", cutoff, RETENTION_BATCH_SIZE),
    ]


def test_retention_rejects_unbounded_adapter_result() -> None:
    class BadPort:
        def rollup_before(self, cutoff):
            del cutoff

        def delete_sensor_batch(self, cutoff, limit):
            del cutoff
            return limit + 1

    with pytest.raises(ValueError):
        run_retention(BadPort(), datetime.now(UTC))


def test_overdue_action_is_finalized_at_two_windows() -> None:
    now = datetime.now(UTC)
    port = FakeRecoveryPort(now)
    deadline = action_terminal_deadline(now - timedelta(minutes=20), timedelta(minutes=10))
    port._actions = [
        RecoverableAction(
            "action-overdue",
            terminal=False,
            has_verification=False,
            terminal_deadline=deadline,
        )
    ]
    report = recover(InMemoryScheduleRepository(), port, now=now)
    assert report.actions_finalized == 1
    assert any(call[:2] == ("finalize", "action-overdue") for call in port.calls)


def test_existing_closing_schedule_is_requeued_for_late_verification() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    closing = Schedule(
        "schedule-closing",
        "PLAN-1-V1",
        "PUMP_01",
        now - timedelta(minutes=10),
        now - timedelta(minutes=5),
        ScheduleStatus.CLOSING,
    )
    repository.add(closing)
    port = FakeRecoveryPort(now)
    report = recover(repository, port, now=now)
    assert report.verifications_queued == 2
    assert closing.late_verification is True
    assert closing.actuator_stopped is True
