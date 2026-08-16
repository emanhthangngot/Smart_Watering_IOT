"""INV-5 recovery contract: an action without verification is re-queued."""

from datetime import UTC, datetime, timedelta

import pytest

from api.recovery import RecoverableAction, action_terminal_deadline, recover
from schedule import InMemoryScheduleRepository

pytestmark = pytest.mark.invariants


class RecoveryPort:
    def __init__(self) -> None:
        self.queued: list[str] = []
        self.keys: set[str] = set()

    def plans(self):
        return []

    def approvals(self):
        return []

    def actions(self):
        return [RecoverableAction("action-1", terminal=False, has_verification=False)]

    def reattach_plan_monitor(self, plan_revision_id):
        raise AssertionError(plan_revision_id)

    def reevaluate_assumptions(self, plan_revision_id):
        raise AssertionError(plan_revision_id)

    def stop_recovered_schedule(self, schedule_id):
        raise AssertionError(schedule_id)

    def expire_approval_and_plan(self, approval_id, plan_revision_id):
        raise AssertionError((approval_id, plan_revision_id))

    def queue_verification(self, identifier, *, late, idempotency_key):
        assert late is False
        if idempotency_key not in self.keys:
            self.keys.add(idempotency_key)
            self.queued.append(identifier)
            return True
        return False

    def finalize_overdue_action_with_verification(self, action_id, *, reason):
        self.queued.append(f"finalized:{action_id}:{reason}")


def test_orphan_action_is_requeued_idempotently_by_port() -> None:
    port = RecoveryPort()
    report = recover(InMemoryScheduleRepository(), port, now=datetime.now(UTC))
    assert report.verifications_queued == 1
    assert port.queued == ["action-1"]
    recover(InMemoryScheduleRepository(), port, now=datetime.now(UTC))
    assert port.queued == ["action-1"]


def test_action_exceeding_two_windows_is_finalized() -> None:
    now = datetime.now(UTC)
    window = timedelta(minutes=10)
    port = RecoveryPort()
    port.actions = lambda: [
        RecoverableAction(
            "action-2",
            terminal=False,
            has_verification=False,
            terminal_deadline=action_terminal_deadline(now - 2 * window, window),
        )
    ]
    report = recover(InMemoryScheduleRepository(), port, now=now)
    assert report.actions_finalized == 1
    assert port.queued[0].startswith("finalized:action-2:")
