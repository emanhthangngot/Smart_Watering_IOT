"""Deterministic five-second schedule runner; no LLM calls."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .claim import ScheduleRepository
from .models import Schedule, ScheduleStatus

TICK_SECONDS = 5
DEFAULT_GRACE_SECONDS = 120
STARTABLE_PLAN_STATUSES = {"APPROVED", "EXECUTING"}
CANCEL_PLAN_STATUSES = {"SUSPENDED", "EXPIRED", "REJECTED", "NEEDS_REPLAN"}


class Actuator(Protocol):
    def start(self, schedule: Schedule) -> None: ...

    def stop(self, schedule: Schedule) -> None: ...


class NoActuation:
    """Observation-only boundary. It intentionally performs no write."""

    def start(self, schedule: Schedule) -> None:
        del schedule

    def stop(self, schedule: Schedule) -> None:
        del schedule


class SimulatorActuation:
    def __init__(self, command: Callable[[str, Schedule], None]) -> None:
        self._command = command

    def start(self, schedule: Schedule) -> None:
        self._command("START", schedule)

    def stop(self, schedule: Schedule) -> None:
        self._command("STOP", schedule)


def actuator_for(
    target: str, simulator_command: Callable[[str, Schedule], None] | None = None
) -> Actuator:
    if target == "none":
        return NoActuation()
    if target == "sim" and simulator_command is not None:
        return SimulatorActuation(simulator_command)
    if target == "sim":
        raise ValueError("sim actuation requires a simulator command adapter")
    raise ValueError(f"unsupported ACTUATION_TARGET: {target!r}")


class ScheduleRunner:
    def __init__(
        self,
        *,
        repository: ScheduleRepository,
        worker_id: str,
        actuator: Actuator,
        plan_status: Callable[[str], str],
        authorize_schedule: Callable[[Schedule], bool],
        tank_level: Callable[[], float | None],
        verify_outcome: Callable[[Schedule], str],
        record_ledger: Callable[[Schedule, str], None],
        available_drawdown_budget: Callable[[], float | None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
        safe_reserve_pct: float = 20.0,
        grace: timedelta = timedelta(seconds=DEFAULT_GRACE_SECONDS),
    ) -> None:
        if not math.isfinite(safe_reserve_pct) or not 0 <= safe_reserve_pct <= 100:
            raise ValueError("safe_reserve_pct must be finite and between 0 and 100")
        if grace <= timedelta(0):
            raise ValueError("grace must be positive")
        self._repository = repository
        self._worker_id = worker_id
        self._actuator = actuator
        self._plan_status = plan_status
        self._authorize_schedule = authorize_schedule
        self._tank_level = tank_level
        self._verify_outcome = verify_outcome
        self._record_ledger = record_ledger
        self._available_drawdown_budget = available_drawdown_budget
        self._on_error = on_error or (lambda _scope, _error: None)
        self._safe_reserve_pct = safe_reserve_pct
        self._grace = grace

    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("runner time must be timezone-aware")
        for schedule in list(self._repository.list_nonterminal()):
            try:
                self._tick_schedule(schedule, now)
            except Exception as error:  # one bad record must never kill the runner loop
                schedule.status_reason = "unexpected runner error; retrying safely"
                self._on_error(schedule.schedule_id, error)

    def _tick_schedule(self, schedule: Schedule, now: datetime) -> None:
        if schedule.status is ScheduleStatus.CLOSING:
            self._verify_closing(schedule, now)
            return
        try:
            plan_status = self._plan_status(schedule.plan_revision_id)
        except Exception as error:
            schedule.status_reason = "authoritative plan state unavailable"
            self._on_error(schedule.schedule_id, error)
            if schedule.status is ScheduleStatus.RUNNING:
                self._cancel(schedule, "authoritative plan state unavailable")
            return
        if plan_status in CANCEL_PLAN_STATUSES:
            self._cancel(schedule, f"plan {plan_status.lower()}")
            return
        if schedule.status in {ScheduleStatus.PENDING, ScheduleStatus.RUNNING}:
            try:
                authorized = self._authorize_schedule(schedule)
            except Exception as error:
                self._on_error(schedule.schedule_id, error)
                authorized = False
            if not authorized:
                self._cancel(schedule, "schedule authorization is missing, stale or expired")
                return
        if schedule.status is ScheduleStatus.PENDING:
            if plan_status in STARTABLE_PLAN_STATUSES:
                self._handle_pending(schedule, now)
        elif schedule.status is ScheduleStatus.RUNNING:
            if plan_status not in STARTABLE_PLAN_STATUSES:
                self._cancel(schedule, f"plan state {plan_status.lower()} is not executable")
            elif now >= schedule.end_at:
                self._close(schedule, now)

    async def run_forever(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as error:
                self._on_error("runner-loop", error)
            await asyncio.sleep(TICK_SECONDS)

    def _handle_pending(self, schedule: Schedule, now: datetime) -> None:
        if now > schedule.start_at + self._grace:
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.MISSED,
                reason="start window exceeded grace; no catch-up",
            )
            return
        if now < schedule.start_at:
            return
        level = self._tank_level()
        if level is None or not math.isfinite(level) or not 0 <= level <= 100:
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.CANCELLED,
                reason="tank evidence missing, non-finite or outside 0..100",
            )
            return
        if level < self._safe_reserve_pct:
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.CANCELLED,
                reason="tank evidence missing or below safe reserve",
            )
            return
        if (
            not math.isfinite(schedule.planned_drawdown_pct)
            or not math.isfinite(schedule.planned_pump_minutes)
            or schedule.planned_drawdown_pct <= 0
            or schedule.planned_pump_minutes <= 0
        ):
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.CANCELLED,
                reason="positive planned drawdown and pump minutes are required",
            )
            return
        budget = (
            self._available_drawdown_budget()
            if self._available_drawdown_budget is not None
            else None
        )
        if budget is None or not math.isfinite(budget) or budget < 0:
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.CANCELLED,
                reason="daily water budget is unavailable or invalid",
            )
            return
        if schedule.planned_drawdown_pct > budget:
            self._repository.transition(
                schedule.schedule_id,
                expected={ScheduleStatus.PENDING},
                target=ScheduleStatus.CANCELLED,
                reason="planned drawdown exceeds available daily water budget",
            )
            return
        if self._repository.try_claim(schedule.schedule_id, self._worker_id):
            claimed = self._repository.get(schedule.schedule_id)
            if claimed is not None:
                try:
                    self._actuator.start(claimed)
                except Exception as error:
                    self._on_error(schedule.schedule_id, error)
                    try:
                        self._actuator.stop(claimed)
                        claimed.actuator_stopped = True
                    except Exception as stop_error:
                        self._on_error(schedule.schedule_id, stop_error)
                        claimed.closing_failure = "actuator start and compensating stop failed"
                    else:
                        claimed.closing_failure = "actuator start outcome uncertain"
                    self._repository.transition(
                        schedule.schedule_id,
                        expected={ScheduleStatus.RUNNING},
                        target=ScheduleStatus.CLOSING,
                        reason=claimed.closing_failure,
                    )
                    claimed.closing_started_at = now
                    self._finalize(
                        claimed,
                        "INCONCLUSIVE",
                        ScheduleStatus.FAILED,
                        claimed.closing_failure,
                    )

    def _close(self, schedule: Schedule, now: datetime) -> None:
        if not self._repository.transition(
            schedule.schedule_id,
            expected={ScheduleStatus.RUNNING},
            target=ScheduleStatus.CLOSING,
        ):
            return
        schedule.closing_started_at = now
        try:
            self._actuator.stop(schedule)
            schedule.actuator_stopped = True
        except Exception as error:
            self._on_error(schedule.schedule_id, error)
            schedule.closing_failure = "actuator stop failed"
            self._finalize(schedule, "INCONCLUSIVE", ScheduleStatus.FAILED, "actuator stop failed")
            return
        self._verify_closing(schedule, now)

    def _verify_closing(self, schedule: Schedule, now: datetime) -> None:
        schedule.verification_attempts += 1
        if schedule.closing_failure is not None:
            self._finalize(
                schedule,
                "INCONCLUSIVE",
                ScheduleStatus.FAILED,
                schedule.closing_failure,
            )
            return
        try:
            result = self._verify_outcome(schedule)
            if result not in {"PASS", "FAIL", "INCONCLUSIVE"}:
                raise ValueError(f"unsupported verification result: {result!r}")
            target = ScheduleStatus.FAILED if result == "FAIL" else ScheduleStatus.DONE
            self._finalize(schedule, result, target, f"outcome verification: {result}")
        except Exception as error:
            self._on_error(schedule.schedule_id, error)
            schedule.status_reason = "outcome verification unavailable; retry pending"
            duration = schedule.end_at - schedule.start_at
            if now >= schedule.end_at + (2 * duration):
                self._finalize(
                    schedule,
                    "INCONCLUSIVE",
                    ScheduleStatus.FAILED,
                    "verification deadline exceeded",
                )

    def _finalize(
        self,
        schedule: Schedule,
        result: str,
        target: ScheduleStatus,
        reason: str,
    ) -> None:
        schedule.verification_result = result
        try:
            self._record_ledger(schedule, result)
        except Exception as error:
            schedule.status_reason = "water ledger write unavailable; retry pending"
            self._on_error(schedule.schedule_id, error)
            return
        self._repository.transition(
            schedule.schedule_id,
            expected={ScheduleStatus.CLOSING},
            target=target,
            reason=reason,
        )

    def _cancel(self, schedule: Schedule, reason: str) -> None:
        if schedule.status is ScheduleStatus.RUNNING:
            try:
                self._actuator.stop(schedule)
                schedule.actuator_stopped = True
            except Exception as error:
                self._on_error(schedule.schedule_id, error)
                self._repository.transition(
                    schedule.schedule_id,
                    expected={ScheduleStatus.RUNNING},
                    target=ScheduleStatus.FAILED,
                    reason="actuator stop failed during cancellation",
                )
                return
            schedule.verification_result = "INCONCLUSIVE"
            try:
                self._record_ledger(schedule, "INCONCLUSIVE")
            except Exception as error:
                self._on_error(schedule.schedule_id, error)
                self._repository.transition(
                    schedule.schedule_id,
                    expected={ScheduleStatus.RUNNING},
                    target=ScheduleStatus.FAILED,
                    reason="water ledger write failed during cancellation",
                )
                return
        self._repository.transition(
            schedule.schedule_id,
            expected={ScheduleStatus.PENDING, ScheduleStatus.RUNNING, ScheduleStatus.CLOSING},
            target=ScheduleStatus.CANCELLED,
            reason=reason,
        )
