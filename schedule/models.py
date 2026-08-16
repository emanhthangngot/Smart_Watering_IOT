"""Schedule state model from plan §9.1."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ScheduleStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CLOSING = "CLOSING"
    DONE = "DONE"
    FAILED = "FAILED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = {
    ScheduleStatus.DONE,
    ScheduleStatus.FAILED,
    ScheduleStatus.MISSED,
    ScheduleStatus.CANCELLED,
}


@dataclass
class Schedule:
    schedule_id: str
    plan_revision_id: str
    pump_id: str
    start_at: datetime
    end_at: datetime
    status: ScheduleStatus = ScheduleStatus.PENDING
    claimed_by: str | None = None
    verification_result: str | None = None
    late_verification: bool = False
    status_reason: str | None = None
    planned_drawdown_pct: float = 0.0
    planned_pump_minutes: float = 0.0
    closing_started_at: datetime | None = None
    closing_failure: str | None = None
    actuator_stopped: bool = False
    verification_attempts: int = 0

    def __post_init__(self) -> None:
        if not self.schedule_id or not self.plan_revision_id or not self.pump_id:
            raise ValueError("schedule, plan revision and pump ids are required")
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("schedule timestamps must be timezone-aware")
        if self.end_at <= self.start_at:
            raise ValueError("schedule end_at must be after start_at")
        for name, value in (
            ("planned_drawdown_pct", self.planned_drawdown_pct),
            ("planned_pump_minutes", self.planned_pump_minutes),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
