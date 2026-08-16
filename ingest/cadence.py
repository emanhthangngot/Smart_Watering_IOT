"""EWMA batch cadence and TTL/freshness derived from it.

Design reference: plans/reports/plan.md §3.5. Cadence is unknown before the
competition, so TTL is stored in `ttl_batches` (registry/specs.py) and
converted to seconds here using the observed batch period — never a
hard-coded second count.
"""

from __future__ import annotations

ALPHA = 0.2
BOOTSTRAP_PERIOD_S = 10.0
BOOTSTRAP_BATCHES = 5

TTL_FLOOR_S = 15.0
TTL_CEIL_S = 1800.0


class CadenceTracker:
    """EWMA of the inter-batch period, bootstrapped at 10s for the first
    5 batches (not enough samples yet to trust an EWMA estimate)."""

    def __init__(self) -> None:
        self._observed_period_s: float = BOOTSTRAP_PERIOD_S
        self._batch_count: int = 0
        self._last_event_time: float | None = None

    @property
    def observed_period_s(self) -> float:
        return self._observed_period_s

    @property
    def batch_count(self) -> int:
        return self._batch_count

    def observe(self, event_time: float) -> float:
        """Feed one batch's event_time. Returns the current observed period."""
        if self._last_event_time is not None:
            delta = event_time - self._last_event_time
            if delta > 0 and self._batch_count >= BOOTSTRAP_BATCHES:
                self._observed_period_s = ALPHA * delta + (1 - ALPHA) * self._observed_period_s
        self._last_event_time = event_time
        self._batch_count += 1
        return self._observed_period_s


def ttl_seconds(ttl_batches: int, observed_period_s: float) -> float:
    """ttl(metric) = clamp(ttl_batches × observed_batch_period, 15s, 1800s)."""
    raw = ttl_batches * observed_period_s
    return max(TTL_FLOOR_S, min(TTL_CEIL_S, raw))


def freshness(age_s: float, ttl_s: float) -> float:
    """§3.5 freshness curve: 1.0 within ttl, linear decay to 0 by 3×ttl."""
    if age_s <= ttl_s:
        return 1.0
    if age_s >= 3 * ttl_s:
        return 0.0
    return 1 - (age_s - ttl_s) / (2 * ttl_s)
