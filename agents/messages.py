"""M3-owned ephemeral projections, not replacements for shared contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .vocabulary import InteractionVerb


@dataclass(frozen=True, slots=True)
class RouteSignal:
    signal_id: str
    source_participant: str
    verb: InteractionVerb
    blocking: bool
    source_state_version: int


@dataclass(frozen=True, slots=True)
class RouteDecision:
    next_participant: str
    event: InteractionVerb
    source_state_version: int
    accepted_signal_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResourceInput:
    level_pct: Decimal | float | int | None
    safe_reserve_pct: Decimal | float | int | None
    active_reserved_drawdown_pct: Decimal | float | int | None
    requested_drawdown_pct: Decimal | float | int | None
    farm_day: str | None
    timezone: str | None
    schedule_conflicts: tuple[str, ...] = ()
    ledger_as_of: datetime | None = None
    now: datetime | None = None
    ledger_max_age_seconds: int = 300
    source_state_version: int | None = None


@dataclass(frozen=True, slots=True)
class ResourceAssessment:
    accepted: bool
    blocking: bool
    needs_more_evidence: bool
    reason: str
    available_drawdown_pct: Decimal | None
    source_state_version: int | None


__all__ = ["ResourceAssessment", "ResourceInput", "RouteDecision", "RouteSignal"]
