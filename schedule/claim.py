"""Atomic schedule claim port plus a lock-safe local implementation."""

from __future__ import annotations

import threading
from typing import Protocol

from .models import TERMINAL_STATUSES, Schedule, ScheduleStatus


class ScheduleConflict(RuntimeError):
    pass


class ScheduleRepository(Protocol):
    def add(self, schedule: Schedule) -> None: ...

    def get(self, schedule_id: str) -> Schedule | None: ...

    def list_nonterminal(self) -> list[Schedule]: ...

    def try_claim(self, schedule_id: str, worker_id: str) -> bool: ...

    def transition(
        self,
        schedule_id: str,
        *,
        expected: set[ScheduleStatus],
        target: ScheduleStatus,
        reason: str | None = None,
    ) -> bool: ...


class InMemoryScheduleRepository:
    """Local adapter mirroring the DB transaction/partial-index semantics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: dict[str, Schedule] = {}

    def add(self, schedule: Schedule) -> None:
        with self._lock:
            if schedule.schedule_id in self._rows:
                raise ScheduleConflict(f"duplicate schedule: {schedule.schedule_id}")
            if schedule.status is ScheduleStatus.RUNNING:
                self._assert_pump_available(schedule.pump_id)
            self._rows[schedule.schedule_id] = schedule

    def get(self, schedule_id: str) -> Schedule | None:
        with self._lock:
            return self._rows.get(schedule_id)

    def list_nonterminal(self) -> list[Schedule]:
        with self._lock:
            return [row for row in self._rows.values() if row.status not in TERMINAL_STATUSES]

    def try_claim(self, schedule_id: str, worker_id: str) -> bool:
        with self._lock:
            row = self._rows.get(schedule_id)
            if row is None or row.status is not ScheduleStatus.PENDING:
                return False
            try:
                self._assert_pump_available(row.pump_id)
            except ScheduleConflict:
                return False
            row.status = ScheduleStatus.RUNNING
            row.claimed_by = worker_id
            return True

    def transition(
        self,
        schedule_id: str,
        *,
        expected: set[ScheduleStatus],
        target: ScheduleStatus,
        reason: str | None = None,
    ) -> bool:
        with self._lock:
            row = self._rows.get(schedule_id)
            if row is None or row.status not in expected:
                return False
            if target is ScheduleStatus.RUNNING:
                self._assert_pump_available(row.pump_id, excluding=schedule_id)
            row.status = target
            row.status_reason = reason
            return True

    def _assert_pump_available(self, pump_id: str, excluding: str | None = None) -> None:
        if any(
            row.pump_id == pump_id
            and row.status is ScheduleStatus.RUNNING
            and row.schedule_id != excluding
            for row in self._rows.values()
        ):
            raise ScheduleConflict(f"pump already RUNNING: {pump_id}")
