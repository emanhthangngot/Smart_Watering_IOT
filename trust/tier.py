"""Tier hysteresis and dwell state machine (§4.5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class Tier(StrEnum):
    INVESTIGATE = "INVESTIGATE"
    PROPOSE = "PROPOSE"
    AUTO = "AUTO"


@dataclass(frozen=True)
class TierState:
    tier: Tier | None = None
    last_changed: datetime | None = None
    raise_streak: int = 0


def tier_for_dcs(dcs: float) -> Tier:
    if dcs >= 0.85:
        return Tier.AUTO
    if dcs >= 0.50:
        return Tier.PROPOSE
    return Tier.INVESTIGATE


def evaluate_tier(
    dcs: float, state: TierState | None = None, now: datetime | None = None
) -> TierState:
    now = now or datetime.now(UTC)
    state = state or TierState()
    target = tier_for_dcs(dcs)
    if state.tier is None:
        return TierState(target, now, 0)
    current = state.tier
    drop = (current is Tier.AUTO and dcs < 0.80) or (current is Tier.PROPOSE and dcs < 0.45)
    if drop:
        return TierState(target, now, 0)
    rank = {Tier.INVESTIGATE: 0, Tier.PROPOSE: 1, Tier.AUTO: 2}
    if rank[target] <= rank[current]:
        return TierState(current, state.last_changed, 0)
    streak = state.raise_streak + 1
    dwell_ok = state.last_changed is None or now - state.last_changed >= timedelta(seconds=60)
    if streak >= 2 and dwell_ok:
        return TierState(target, now, 0)
    return TierState(current, state.last_changed, streak)
