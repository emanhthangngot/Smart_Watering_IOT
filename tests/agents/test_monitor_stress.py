from datetime import datetime, timedelta

import pytest

from agents.monitor import InvalidationDecision, InvalidationGuard, InvalidationKey

pytestmark = pytest.mark.agents


def test_repeated_one_hz_events_have_one_open_replan_per_window() -> None:
    guard = InvalidationGuard(debounce=timedelta(seconds=5), max_entries=20)
    start = datetime(2026, 1, 1)
    accepted = 0
    for second in range(60):
        at = start + timedelta(seconds=second)
        if guard.accept(
            InvalidationDecision(InvalidationKey("p", f"a{second // 5}", second), "changed", at)
        ):
            accepted += 1
            guard.close_replan("p", f"a{second // 5}")
        guard.cleanup(now=at)
    assert accepted == 12
    assert guard.remembered_events <= 20


def test_watermark_state_is_pruned_with_stale_slots() -> None:
    guard = InvalidationGuard(debounce=timedelta(seconds=1), max_entries=1_000)
    start = datetime(2026, 1, 1)
    for slot in range(1_000):
        at = start + timedelta(seconds=slot)
        assert guard.accept(
            InvalidationDecision(InvalidationKey("p", f"a{slot}", 1), "changed", at)
        )
        guard.close_replan("p", f"a{slot}")
        guard.cleanup(now=at)
    assert len(guard._highest_version_by_slot) <= 5
