"""Startup recovery coordinator for non-terminal records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from schedule.claim import ScheduleRepository
from schedule.models import ScheduleStatus


@dataclass(frozen=True)
class RecoverablePlan:
    plan_revision_id: str
    status: str


@dataclass(frozen=True)
class RecoverableApproval:
    approval_id: str
    plan_revision_id: str
    expires_at: datetime
    revoked: bool = False

    def __post_init__(self) -> None:
        if self.expires_at.tzinfo is None:
            raise ValueError("approval expiry must be timezone-aware")


@dataclass(frozen=True)
class RecoverableAction:
    action_id: str
    terminal: bool
    has_verification: bool
    terminal_deadline: datetime | None = None


class RecoveryPort(Protocol):
    def plans(self) -> list[RecoverablePlan]: ...

    def approvals(self) -> list[RecoverableApproval]: ...

    def actions(self) -> list[RecoverableAction]: ...

    def reattach_plan_monitor(self, plan_revision_id: str) -> None: ...

    def reevaluate_assumptions(self, plan_revision_id: str) -> None: ...

    def stop_recovered_schedule(self, schedule_id: str) -> None: ...

    def expire_approval_and_plan(self, approval_id: str, plan_revision_id: str) -> None: ...

    def queue_verification(
        self,
        action_or_schedule_id: str,
        *,
        late: bool,
        idempotency_key: str,
    ) -> bool: ...

    def finalize_overdue_action_with_verification(self, action_id: str, *, reason: str) -> None: ...


@dataclass(frozen=True)
class RecoveryReport:
    schedules_missed: int = 0
    schedules_closing: int = 0
    plans_reattached: int = 0
    approvals_revoked: int = 0
    verifications_queued: int = 0
    actions_finalized: int = 0


def recover(
    schedules: ScheduleRepository,
    port: RecoveryPort,
    *,
    now: datetime | None = None,
    grace: timedelta = timedelta(minutes=2),
) -> RecoveryReport:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("recovery time must be timezone-aware")
    counts = {
        "missed": 0,
        "closing": 0,
        "plans": 0,
        "approvals": 0,
        "queued": 0,
        "finalized": 0,
    }
    for schedule in schedules.list_nonterminal():
        if schedule.status is ScheduleStatus.PENDING and now > schedule.start_at + grace:
            if schedules.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.MISSED,
                reason="startup recovery: past grace",
            ):
                counts["missed"] += 1
        elif schedule.status is ScheduleStatus.RUNNING and now > schedule.end_at:
            if not schedule.actuator_stopped:
                port.stop_recovered_schedule(schedule.schedule_id)
                schedule.actuator_stopped = True
            if schedules.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.RUNNING},
                target=ScheduleStatus.CLOSING,
                reason="startup recovery: late verification",
            ):
                schedule.late_verification = True
                queued = port.queue_verification(
                    schedule.schedule_id,
                    late=True,
                    idempotency_key=f"verify:schedule:{schedule.schedule_id}",
                )
                counts["closing"] += 1
                counts["queued"] += int(queued)
        elif schedule.status is ScheduleStatus.CLOSING and schedule.verification_result is None:
            if not schedule.actuator_stopped:
                port.stop_recovered_schedule(schedule.schedule_id)
                schedule.actuator_stopped = True
            schedule.late_verification = True
            queued = port.queue_verification(
                schedule.schedule_id,
                late=True,
                idempotency_key=f"verify:schedule:{schedule.schedule_id}",
            )
            counts["queued"] += int(queued)
    for plan in port.plans():
        if plan.status == "EXECUTING":
            port.reattach_plan_monitor(plan.plan_revision_id)
            port.reevaluate_assumptions(plan.plan_revision_id)
            counts["plans"] += 1
    for approval in port.approvals():
        if not approval.revoked and approval.expires_at <= now:
            port.expire_approval_and_plan(approval.approval_id, approval.plan_revision_id)
            counts["approvals"] += 1
    for action in port.actions():
        if (
            not action.terminal
            and action.terminal_deadline is not None
            and action.terminal_deadline <= now
        ):
            port.finalize_overdue_action_with_verification(
                action.action_id,
                reason="startup recovery: exceeded 2x observation window",
            )
            counts["finalized"] += 1
        elif not action.has_verification:
            queued = port.queue_verification(
                action.action_id,
                late=False,
                idempotency_key=f"verify:action:{action.action_id}",
            )
            counts["queued"] += int(queued)
    return RecoveryReport(
        schedules_missed=counts["missed"],
        schedules_closing=counts["closing"],
        plans_reattached=counts["plans"],
        approvals_revoked=counts["approvals"],
        verifications_queued=counts["queued"],
        actions_finalized=counts["finalized"],
    )


def action_terminal_deadline(started_at: datetime, observation_window: timedelta) -> datetime:
    """INV-5 deadline: every action must terminate within two windows."""

    if observation_window <= timedelta(0):
        raise ValueError("observation window must be positive")
    return started_at + (2 * observation_window)
