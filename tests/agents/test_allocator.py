from datetime import datetime, timedelta

import pytest

from agents.allocator import (
    AllocationCandidate,
    AllocationRequest,
    ExistingAllocation,
    StateVersionMismatch,
    TimeWindow,
    allocate,
)

pytestmark = pytest.mark.agents


def window(hour: int) -> TimeWindow:
    start = datetime(2026, 8, 16, hour)
    return TimeWindow(start, start + timedelta(minutes=30))


def candidate(identifier: str, urgency: int, hour: int, drawdown: int = 10) -> AllocationCandidate:
    return AllocationCandidate(identifier, urgency, "PUMP_01", 10, drawdown, window(hour), 60, 20)


def test_ranking_is_stable_and_respects_budget() -> None:
    request = AllocationRequest(
        7,
        (candidate("b", 5, 2), candidate("a", 5, 1)),
        10,
        20,
        (window(1), window(2)),
        resource_state_version=7,
        trust_state_version=7,
    )
    result = allocate(request)
    assert [item.candidate_id for item in result.slices] == ["a"]
    assert result.reasons[0].code == "DRAWDOWN_LIMIT"


def test_no_overlap_allowed_window_and_reserve_constraints_are_explicit() -> None:
    existing = ExistingAllocation("PUMP_01", window(3))
    outside = AllocationCandidate("outside", 10, "PUMP_01", 10, 1, window(5), 60, 20)
    below = AllocationCandidate("below", 9, "PUMP_02", 10, 1, window(6), 10, 20)
    result = allocate(
        AllocationRequest(7, (outside, below), 20, 30, (window(1),), (existing,), 7, 7)
    )
    assert not result.slices
    assert {reason.code for reason in result.reasons} == {
        "OUTSIDE_ALLOWED_WINDOW",
        "TANK_BELOW_RESERVE",
    }


def test_tank_reserve_headroom_is_shared_across_selected_candidates() -> None:
    first = AllocationCandidate("first", 10, "PUMP_01", 10, 30, window(1), 60, 20)
    second = AllocationCandidate("second", 9, "PUMP_01", 10, 30, window(2), 60, 20)
    result = allocate(
        AllocationRequest(
            7,
            (first, second),
            100,
            100,
            (window(1), window(2)),
            resource_state_version=7,
            trust_state_version=7,
        )
    )
    assert [item.candidate_id for item in result.slices] == ["first"]
    assert {(r.candidate_id, r.code) for r in result.reasons} == {("second", "TANK_RESERVE_LIMIT")}


def test_missing_allowed_window_rejects_every_candidate() -> None:
    result = allocate(
        AllocationRequest(
            7, (candidate("a", 1, 1),), 20, 20, resource_state_version=7, trust_state_version=7
        )
    )
    assert not result.slices
    assert [r.code for r in result.reasons] == ["MISSING_ALLOWED_WINDOW"]


def test_missing_tank_fact_fails_closed() -> None:
    bare = AllocationCandidate("bare", 1, "PUMP_01", 10, 5, window(1), None, None)
    result = allocate(
        AllocationRequest(
            7, (bare,), 20, 20, (window(1),), resource_state_version=7, trust_state_version=7
        )
    )
    assert not result.slices
    assert result.reasons[0].code == "MISSING_TANK_FACT"


def test_window_too_short_for_requested_duration() -> None:
    short = AllocationCandidate("short", 1, "PUMP_01", 45, 5, window(1), 60, 20)
    result = allocate(
        AllocationRequest(
            7, (short,), 20, 60, (window(1),), resource_state_version=7, trust_state_version=7
        )
    )
    assert result.reasons[0].code == "WINDOW_TOO_SHORT"


def test_invalid_request_rejects_non_positive_duration_or_negative_drawdown() -> None:
    zero_duration = AllocationCandidate("zero", 1, "PUMP_01", 0, 5, window(1), 60, 20)
    result = allocate(
        AllocationRequest(
            7,
            (zero_duration,),
            20,
            60,
            (window(1),),
            resource_state_version=7,
            trust_state_version=7,
        )
    )
    assert result.reasons[0].code == "INVALID_REQUEST"


def test_pump_overlap_rejects_second_candidate_on_same_pump() -> None:
    first = AllocationCandidate("first", 10, "PUMP_01", 10, 5, window(1), 60, 20)
    overlapping = AllocationCandidate(
        "overlap",
        9,
        "PUMP_01",
        10,
        5,
        TimeWindow(
            window(1).start + timedelta(minutes=10), window(1).start + timedelta(minutes=40)
        ),
        60,
        20,
    )
    result = allocate(
        AllocationRequest(
            7,
            (first, overlapping),
            20,
            60,
            (TimeWindow(window(1).start, window(1).start + timedelta(hours=1)),),
            resource_state_version=7,
            trust_state_version=7,
        )
    )
    assert [item.candidate_id for item in result.slices] == ["first"]
    assert {(r.candidate_id, r.code) for r in result.reasons} == {("overlap", "PUMP_OVERLAP")}


def test_pump_minute_limit_rejects_when_minutes_exhausted() -> None:
    fitted_window = TimeWindow(window(1).start, window(1).start + timedelta(minutes=45))
    slow = AllocationCandidate("slow", 1, "PUMP_01", 45, 5, fitted_window, 60, 20)
    result = allocate(
        AllocationRequest(
            7, (slow,), 20, 30, (fitted_window,), resource_state_version=7, trust_state_version=7
        )
    )
    assert result.reasons[0].code == "PUMP_MINUTE_LIMIT"


def test_version_mismatch_is_rejected_before_ranking() -> None:
    request = AllocationRequest(
        7, (candidate("a", 1, 1),), 20, 20, resource_state_version=6, trust_state_version=7
    )
    with pytest.raises(StateVersionMismatch):
        allocate(request)
