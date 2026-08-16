"""Reading-state assignment for the trust engine (§3.3)."""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Any

from trust._access import field


class ReadingState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    SUSPECT = "SUSPECT"
    OFFLINE = "OFFLINE"
    MISSING = "MISSING"


def assign_state(
    reading: Any | None,
    *,
    present: bool = True,
    absent_batches: int = 0,
    offline_batches: int = 3,
    age: float | None = 0,
    ttl: float | None = 1,
) -> ReadingState:
    """Classify a reading. Unknown/malformed inputs are safe, never evidence."""
    if reading is None:
        return ReadingState.MISSING
    if not present and absent_batches >= offline_batches:
        return ReadingState.OFFLINE
    if field(reading, "source_status", field(reading, "status", "ok")) != "ok":
        return ReadingState.SUSPECT
    try:
        normalized_age = max(0.0, float(age))
        normalized_ttl = float(ttl)
    except (TypeError, ValueError):
        return ReadingState.STALE
    if not isfinite(normalized_age) or not isfinite(normalized_ttl) or normalized_ttl <= 0:
        return ReadingState.STALE
    return ReadingState.FRESH if normalized_age <= normalized_ttl else ReadingState.STALE


def is_usable(state: ReadingState | str | None) -> bool:
    return str(state) in {ReadingState.FRESH, ReadingState.STALE}
