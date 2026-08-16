"""Water ledger accounting in tank-percent, flow-integral and pump-minutes."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class Reconciliation(StrEnum):
    MATCH = "MATCH"
    UNDER_DELIVERED = "UNDER_DELIVERED"
    OVER_DRAWN = "OVER_DRAWN"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class WaterLedgerEntry:
    entry_id: str
    plan_revision_id: str
    action_id: str
    window_start: datetime
    window_end: datetime
    planned_drawdown_pct: float
    planned_pump_minutes: float
    observed_tank_drawdown_pct: float | None
    observed_flow_integral: float | None
    observed_pump_minutes: float | None
    reconciliation: Reconciliation
    active: bool = False

    def __post_init__(self) -> None:
        if not self.entry_id or not self.plan_revision_id or not self.action_id:
            raise ValueError("ledger, plan revision and action ids are required")
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("ledger timestamps must be timezone-aware")
        if self.window_end < self.window_start:
            raise ValueError("ledger window_end cannot precede window_start")
        for name, value in (
            ("planned_drawdown_pct", self.planned_drawdown_pct),
            ("planned_pump_minutes", self.planned_pump_minutes),
            ("observed_tank_drawdown_pct", self.observed_tank_drawdown_pct),
            ("observed_flow_integral", self.observed_flow_integral),
            ("observed_pump_minutes", self.observed_pump_minutes),
        ):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and non-negative")


class WaterLedgerRepository(Protocol):
    def add(self, entry: WaterLedgerEntry) -> None: ...

    def list_for_day(self, day: datetime) -> list[WaterLedgerEntry]: ...


class InMemoryWaterLedger:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, WaterLedgerEntry] = {}

    @property
    def entries(self) -> list[WaterLedgerEntry]:
        with self._lock:
            return list(self._entries.values())

    def add(self, entry: WaterLedgerEntry) -> None:
        with self._lock:
            current = self._entries.get(entry.entry_id)
            if current is not None and current != entry:
                raise ValueError(f"conflicting ledger entry: {entry.entry_id}")
            self._entries[entry.entry_id] = entry

    def list_for_day(self, day: datetime) -> list[WaterLedgerEntry]:
        with self._lock:
            return [
                entry for entry in self._entries.values() if entry.window_start.date() == day.date()
            ]

    def record_schedule(self, schedule: object, result: str) -> None:
        """Idempotent local writer matching the runner's ledger callback contract."""

        from schedule.models import Schedule

        if not isinstance(schedule, Schedule):
            raise TypeError("schedule ledger writer requires a Schedule")
        if result not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise ValueError(f"unsupported outcome result: {result!r}")
        self.add(
            WaterLedgerEntry(
                entry_id=f"ledger:{schedule.schedule_id}",
                plan_revision_id=schedule.plan_revision_id,
                action_id=schedule.schedule_id,
                window_start=schedule.start_at,
                window_end=schedule.end_at,
                planned_drawdown_pct=schedule.planned_drawdown_pct,
                planned_pump_minutes=schedule.planned_pump_minutes,
                observed_tank_drawdown_pct=None,
                observed_flow_integral=None,
                observed_pump_minutes=None,
                # Outcome verification and water reconciliation are separate.
                # Without observed tank/flow inputs this must remain honest.
                reconciliation=Reconciliation.INCONCLUSIVE,
                active=False,
            )
        )


def reconcile(
    *,
    observed_tank_drawdown_pct: float | None,
    observed_flow_integral: float | None,
    expected_drawdown_per_flow_unit: float | None,
    readings_usable: bool,
    tolerance_fraction: float = 0.20,
) -> Reconciliation:
    if not math.isfinite(tolerance_fraction) or not 0 <= tolerance_fraction < 1:
        raise ValueError("tolerance_fraction must be finite and in [0, 1)")
    if (
        not readings_usable
        or observed_tank_drawdown_pct is None
        or observed_flow_integral is None
        or expected_drawdown_per_flow_unit is None
        or not math.isfinite(observed_tank_drawdown_pct)
        or not math.isfinite(observed_flow_integral)
        or not math.isfinite(expected_drawdown_per_flow_unit)
        or observed_tank_drawdown_pct < 0
        or observed_flow_integral <= 0
        or expected_drawdown_per_flow_unit <= 0
    ):
        return Reconciliation.INCONCLUSIVE
    expected_drawdown = observed_flow_integral * expected_drawdown_per_flow_unit
    lower = expected_drawdown * (1 - tolerance_fraction)
    upper = expected_drawdown * (1 + tolerance_fraction)
    if observed_tank_drawdown_pct < lower:
        return Reconciliation.UNDER_DELIVERED
    if observed_tank_drawdown_pct > upper:
        return Reconciliation.OVER_DRAWN
    return Reconciliation.MATCH


def active_planned_drawdown(repository: WaterLedgerRepository, day: datetime) -> float:
    return sum(entry.planned_drawdown_pct for entry in repository.list_for_day(day) if entry.active)


def available_drawdown_budget(
    level_now: float, safe_reserve_pct: float, committed_pct: float
) -> float:
    values = (level_now, safe_reserve_pct, committed_pct)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("water budget inputs must be finite")
    if not 0 <= level_now <= 100 or not 0 <= safe_reserve_pct <= 100:
        raise ValueError("tank level and safe reserve must be between 0 and 100")
    if committed_pct < 0:
        raise ValueError("committed drawdown cannot be negative")
    return max(0.0, level_now - safe_reserve_pct - committed_pct)
