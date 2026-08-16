from datetime import datetime

import pytest

from worldstate.llm_slice import ForbiddenStateKey, build_llm_slice
from worldstate.state import WorldState

pytestmark = pytest.mark.agents


def test_slice_keeps_only_allowlisted_nested_paths_and_is_immutable() -> None:
    state = WorldState()
    snapshot = state.apply(
        "telemetry",
        {"latest": [{"metric": "level", "value": 50, "secret": "omit"}], "windows": []},
        at=datetime(2026, 1, 1),
    )
    sliced = build_llm_slice(snapshot, ["telemetry.latest.metric", "telemetry.latest.value"])

    assert sliced == {"telemetry": {"latest": ({"metric": "level", "value": 50},)}}
    with pytest.raises(TypeError):
        sliced["telemetry"] = {}


def test_nested_forbidden_scenario_is_rejected_before_projection() -> None:
    state = WorldState()
    snapshot = state.apply(
        "telemetry", {"latest": [{"scenario": "NORMAL", "value": 1}]}, at=datetime(2026, 1, 1)
    )
    with pytest.raises(ForbiddenStateKey):
        build_llm_slice(snapshot, ["telemetry.latest.value"])


def test_unknown_paths_are_omitted() -> None:
    state = WorldState()
    snapshot = state.apply("telemetry", {"latest": [1]}, at=datetime(2026, 1, 1))
    assert build_llm_slice(snapshot, ["telemetry.missing"]) == {}


def test_nested_projection_drops_items_without_a_matching_path() -> None:
    state = WorldState()
    snapshot = state.apply(
        "telemetry", {"latest": [{"value": 1}, {"other": 2}]}, at=datetime(2026, 1, 1)
    )
    assert build_llm_slice(snapshot, ["telemetry.latest.value"]) == {
        "telemetry": {"latest": ({"value": 1},)}
    }


def test_subtree_projection_requires_explicit_wildcard() -> None:
    state = WorldState()
    snapshot = state.apply(
        "telemetry", {"latest": {"value": 1, "unit": "%"}}, at=datetime(2026, 1, 1)
    )
    assert build_llm_slice(snapshot, ["telemetry.latest"]) == {}
    assert build_llm_slice(snapshot, ["telemetry.latest.*"]) == {
        "telemetry": {"latest": {"value": 1, "unit": "%"}}
    }
