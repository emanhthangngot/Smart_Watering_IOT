"""registry/specs.py — G0 contract checks. plans/reports/plan.md §3.6."""

from __future__ import annotations

import pytest

from registry.specs import SPECS, get_spec, is_required, wsum


@pytest.mark.data_plane
def test_wsum_matches_frozen_contract():
    assert wsum("irrigation_plan") == 13
    assert wsum("session_check") == 9
    assert wsum("tank_quality") == 5


@pytest.mark.data_plane
def test_nine_rows_no_more_no_less():
    assert len(SPECS) == 9


@pytest.mark.data_plane
def test_required_flags_match_section_3_6():
    assert is_required("SOIL_01", "soil_moisture", "irrigation_plan")
    assert is_required("SOIL_01", "soil_moisture", "session_check")
    assert not is_required("SOIL_01", "soil_moisture", "tank_quality")
    assert is_required("PUMP_01", "flow_rate", "session_check")
    assert not is_required("PUMP_01", "flow_rate", "irrigation_plan")
    assert is_required("PH_01", "ph", "tank_quality")
    assert is_required("TANK_01", "level", "irrigation_plan")
    assert not is_required("TANK_01", "level", "session_check")


@pytest.mark.data_plane
def test_unknown_metric_returns_none():
    assert get_spec("SOIL_01", "not_a_metric") is None
    assert get_spec("NOT_A_DEVICE", "ph") is None


@pytest.mark.data_plane
def test_payload_metric_set_matches_registry_exactly():
    """§3.1 point 6: the real payload's metric set matches this table
    exactly — no extra, no missing."""
    payload_metrics = {
        ("PH_01", "ph"),
        ("PUMP_01", "flow_rate"),
        ("PUMP_01", "power"),
        ("SOIL_01", "soil_moisture"),
        ("SOIL_01", "temperature"),
        ("SUN_01", "lux"),
        ("TANK_01", "level"),
        ("WEATHER_01", "temperature"),
        ("WEATHER_01", "humidity"),
    }
    registry_metrics = {spec.key for spec in SPECS}
    assert payload_metrics == registry_metrics
