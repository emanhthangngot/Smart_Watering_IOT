from datetime import datetime, timedelta

import pytest

from agents.monitor import (
    InvalidationDecision,
    InvalidationGuard,
    InvalidationKey,
    evaluate_changes,
    select_touched_assumptions,
)

pytestmark = pytest.mark.agents


def decision(version: int, at: datetime) -> InvalidationDecision:
    return InvalidationDecision(InvalidationKey("p1", "a1", version), "changed", at)


def test_only_touched_assumptions_are_evaluated() -> None:
    assert select_touched_assumptions({"level"}, {"a2": {"flow"}, "a1": {"level"}}) == ("a1",)
    called = []
    now = datetime(2026, 1, 1)
    result = evaluate_changes(
        {"level"},
        {"a1": {"level"}, "a2": {"flow"}},
        now=now,
        evaluator=lambda assumption, changed, at: called.append(assumption) or decision(1, at),
    )
    assert called == ["a1"] and len(result) == 1


def test_duplicate_debounce_and_one_open_replan() -> None:
    guard = InvalidationGuard(debounce=timedelta(seconds=10))
    first = decision(1, datetime(2026, 1, 1))
    assert guard.accept(first)
    assert not guard.accept(first)
    assert not guard.accept(decision(2, datetime(2026, 1, 1, 0, 0, 5)))
    guard.close_replan("p1", "a1")
    assert guard.accept(decision(2, datetime(2026, 1, 1, 0, 0, 20)))


def test_cleanup_is_bounded_and_does_not_remove_open_slot() -> None:
    guard = InvalidationGuard(debounce=timedelta(seconds=1), max_entries=2)
    base = datetime(2026, 1, 1)
    assert guard.accept(decision(1, base))
    guard.close_replan("p1", "a1")
    guard.accept(
        InvalidationDecision(InvalidationKey("p1", "a2", 2), "changed", base + timedelta(seconds=2))
    )
    guard.cleanup(now=base + timedelta(seconds=4))
    assert guard.remembered_events == 0


def test_exact_duplicate_remains_rejected_after_event_cache_trim() -> None:
    guard = InvalidationGuard(debounce=timedelta(seconds=1), max_entries=1)
    base = datetime(2026, 1, 1)
    first = decision(1, base)
    assert guard.accept(first)
    guard.close_replan("p1", "a1")
    assert guard.accept(
        InvalidationDecision(InvalidationKey("p1", "a2", 2), "changed", base + timedelta(seconds=2))
    )
    guard.close_replan("p1", "a2")
    assert not guard.accept(first)
