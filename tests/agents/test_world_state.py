from datetime import UTC, datetime

import pytest

from worldstate.state import (
    FarmStateSnapshot,
    InvalidStateSection,
    StateVersionNotFound,
    WorldState,
)

pytestmark = pytest.mark.agents


def test_initial_and_sequential_versions_are_monotonic() -> None:
    state = WorldState()
    first_time = datetime(2026, 8, 16, tzinfo=UTC)
    second_time = datetime(2026, 8, 16, 0, 0, 1, tzinfo=UTC)

    assert state.current().state_version == 0
    first = state.apply("telemetry", {"latest": [1]}, at=first_time)
    second = state.apply("resources", {"tank": 50}, at=second_time)

    assert (first.state_version, second.state_version) == (1, 2)
    assert state.at(1).telemetry == {"latest": (1,)}
    assert state.at(2).resources == {"tank": 50}
    assert state.at(1).updated_at == first_time


def test_snapshots_are_historical_and_deeply_immutable() -> None:
    state = WorldState()
    source = {"latest": [{"value": 10}]}
    first = state.apply("telemetry", source, at=datetime(2026, 1, 1))
    source["latest"][0]["value"] = 99
    state.apply("telemetry", {"latest": [{"value": 20}]}, at=datetime(2026, 1, 2))

    assert first.telemetry["latest"][0]["value"] == 10
    with pytest.raises(TypeError):
        first.telemetry["latest"][0]["value"] = 11


def test_invalid_section_and_missing_version_fail_without_mutation() -> None:
    state = WorldState()
    with pytest.raises(InvalidStateSection):
        state.apply("scenario", "NORMAL", at=datetime(2026, 1, 1))
    with pytest.raises(StateVersionNotFound):
        state.at(99)
    assert state.current().state_version == 0


def test_fixed_replay_produces_equivalent_snapshots() -> None:
    updates = [("telemetry", {"x": 1}), ("trust", {"scope": "AUTO"})]
    timestamp = datetime(2026, 1, 1)
    left = WorldState()
    right = WorldState()
    for section, value in updates:
        left.apply(section, value, at=timestamp)
        right.apply(section, value, at=timestamp)
    assert left.current() == right.current()


def test_direct_snapshot_construction_freezes_external_mapping() -> None:
    sections = {"telemetry": {"latest": [{"value": 1}]}}
    snapshot = FarmStateSnapshot(1, datetime(2026, 1, 1), sections)
    sections["telemetry"]["latest"][0]["value"] = 9
    assert snapshot.telemetry["latest"][0]["value"] == 1


def test_mutable_leaf_is_rejected() -> None:
    with pytest.raises(TypeError, match="unsupported mutable snapshot leaf"):
        FarmStateSnapshot(1, datetime(2026, 1, 1), {"telemetry": {"raw": bytearray(b"x")}})
