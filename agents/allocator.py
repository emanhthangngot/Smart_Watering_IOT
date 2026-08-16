"""Deterministic irrigation allocation kernel."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


class AllocationInputError(ValueError):
    """Raised when allocation facts are incomplete or version-inconsistent."""


class StateVersionMismatch(AllocationInputError):
    """Raised before ranking when a projection is from another state version."""


def _d(value: Decimal | float | int, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AllocationInputError(f"invalid {field}") from exc
    if not result.is_finite():
        raise AllocationInputError(f"invalid {field}")
    return result


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise AllocationInputError("window end must be after start")


@dataclass(frozen=True, slots=True)
class AllocationCandidate:
    candidate_id: str
    urgency: Decimal | float | int
    pump_id: str
    duration_minutes: Decimal | float | int
    drawdown_pct: Decimal | float | int
    window: TimeWindow
    tank_level_pct: Decimal | float | int | None = None
    safe_reserve_pct: Decimal | float | int | None = None


@dataclass(frozen=True, slots=True)
class ExistingAllocation:
    pump_id: str
    window: TimeWindow


@dataclass(frozen=True, slots=True)
class AllocationRequest:
    source_state_version: int
    candidates: tuple[AllocationCandidate, ...] = ()
    available_drawdown_pct: Decimal | float | int = 0
    available_pump_minutes: Decimal | float | int = 0
    allowed_windows: tuple[TimeWindow, ...] = ()
    existing_allocations: tuple[ExistingAllocation, ...] = ()
    resource_state_version: int | None = None
    trust_state_version: int | None = None


@dataclass(frozen=True, slots=True)
class AllocationSlice:
    candidate_id: str
    pump_id: str
    window: TimeWindow
    duration_minutes: Decimal
    drawdown_pct: Decimal


@dataclass(frozen=True, slots=True)
class AllocationReason:
    candidate_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class AllocationResult:
    source_state_version: int
    slices: tuple[AllocationSlice, ...]
    reasons: tuple[AllocationReason, ...]
    narrative: str = ""

    @property
    def quantitative_fields(self) -> tuple[AllocationSlice, ...]:
        return self.slices


def _overlaps(left: TimeWindow, right: TimeWindow) -> bool:
    return left.start < right.end and right.start < left.end


def _fits_allowed(candidate: AllocationCandidate, allowed: tuple[TimeWindow, ...]) -> bool:
    return not allowed or any(
        window.start <= candidate.window.start and candidate.window.end <= window.end
        for window in allowed
    )


def allocate(request: AllocationRequest) -> AllocationResult:
    if request.resource_state_version is None or request.trust_state_version is None:
        raise StateVersionMismatch(
            "resource and trust projections must include source state version"
        )
    versions = {
        version
        for version in (request.resource_state_version, request.trust_state_version)
        if version is not None
    }
    if versions and versions != {request.source_state_version}:
        raise StateVersionMismatch("resource/trust projection does not match source state version")
    remaining_drawdown = _d(request.available_drawdown_pct, "available_drawdown_pct")
    remaining_minutes = _d(request.available_pump_minutes, "available_pump_minutes")
    existing = tuple(request.existing_allocations)
    ranked = sorted(
        request.candidates, key=lambda item: (-_d(item.urgency, "urgency"), item.candidate_id)
    )
    selected: list[AllocationSlice] = []
    reasons: list[AllocationReason] = []
    remaining_headroom: dict[str, Decimal] = {}
    if not request.allowed_windows:
        return AllocationResult(
            request.source_state_version,
            (),
            tuple(
                AllocationReason(
                    item.candidate_id,
                    "MISSING_ALLOWED_WINDOW",
                    "allowed scheduling window is missing",
                )
                for item in ranked
            ),
        )
    for candidate in ranked:
        duration = _d(candidate.duration_minutes, "duration_minutes")
        drawdown = _d(candidate.drawdown_pct, "drawdown_pct")
        if candidate.tank_level_pct is None or candidate.safe_reserve_pct is None:
            reasons.append(
                AllocationReason(
                    candidate.candidate_id,
                    "MISSING_TANK_FACT",
                    "tank level and safe reserve are required",
                )
            )
            continue
        if _d(candidate.tank_level_pct, "tank_level_pct") < _d(
            candidate.safe_reserve_pct, "safe_reserve_pct"
        ):
            reasons.append(
                AllocationReason(
                    candidate.candidate_id, "TANK_BELOW_RESERVE", "tank is below safe reserve"
                )
            )
            continue
        headroom = remaining_headroom.setdefault(
            candidate.pump_id,
            max(
                Decimal(0),
                _d(candidate.tank_level_pct, "tank_level_pct")
                - _d(candidate.safe_reserve_pct, "safe_reserve_pct"),
            ),
        )
        if drawdown > headroom:
            reasons.append(
                AllocationReason(
                    candidate.candidate_id,
                    "TANK_RESERVE_LIMIT",
                    "candidate drawdown exceeds tank reserve headroom",
                )
            )
            continue
        if duration <= 0 or drawdown < 0:
            reasons.append(
                AllocationReason(
                    candidate.candidate_id, "INVALID_REQUEST", "duration and drawdown are invalid"
                )
            )
            continue
        if candidate.window.end - candidate.window.start < timedelta(minutes=float(duration)):
            reasons.append(
                AllocationReason(
                    candidate.candidate_id, "WINDOW_TOO_SHORT", "candidate does not fit its window"
                )
            )
            continue
        if not _fits_allowed(candidate, request.allowed_windows):
            reasons.append(
                AllocationReason(
                    candidate.candidate_id,
                    "OUTSIDE_ALLOWED_WINDOW",
                    "candidate is outside an allowed window",
                )
            )
            continue
        if any(
            item.pump_id == candidate.pump_id and _overlaps(item.window, candidate.window)
            for item in existing + tuple(selected_as_existing(selected))
        ):
            reasons.append(
                AllocationReason(
                    candidate.candidate_id,
                    "PUMP_OVERLAP",
                    "pump window overlaps another allocation",
                )
            )
            continue
        if drawdown > remaining_drawdown:
            reasons.append(
                AllocationReason(
                    candidate.candidate_id, "DRAWDOWN_LIMIT", "daily drawdown budget is exhausted"
                )
            )
            continue
        if duration > remaining_minutes:
            reasons.append(
                AllocationReason(
                    candidate.candidate_id, "PUMP_MINUTE_LIMIT", "pump-minute budget is exhausted"
                )
            )
            continue
        selected.append(
            AllocationSlice(
                candidate.candidate_id, candidate.pump_id, candidate.window, duration, drawdown
            )
        )
        remaining_drawdown -= drawdown
        remaining_minutes -= duration
        remaining_headroom[candidate.pump_id] -= drawdown
    return AllocationResult(request.source_state_version, tuple(selected), tuple(reasons))


def selected_as_existing(selected: Iterable[AllocationSlice]) -> Iterable[ExistingAllocation]:
    return (ExistingAllocation(item.pump_id, item.window) for item in selected)


__all__ = [
    "AllocationCandidate",
    "AllocationInputError",
    "AllocationReason",
    "AllocationRequest",
    "AllocationResult",
    "AllocationSlice",
    "ExistingAllocation",
    "StateVersionMismatch",
    "TimeWindow",
    "allocate",
]
