"""Freshness scoring derived from a metric's observed TTL."""

from __future__ import annotations

from math import isfinite


def freshness(age: float | None, ttl: float | None) -> float:
    """Return the §3.5 piecewise freshness score, without raising."""
    try:
        normalized_age = max(0.0, float(age))
        normalized_ttl = float(ttl)
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(normalized_age) or not isfinite(normalized_ttl) or normalized_ttl <= 0:
        return 0.0
    if normalized_age <= normalized_ttl:
        return 1.0
    if normalized_age >= 3 * normalized_ttl:
        return 0.0
    return 1.0 - (normalized_age - normalized_ttl) / (2 * normalized_ttl)
