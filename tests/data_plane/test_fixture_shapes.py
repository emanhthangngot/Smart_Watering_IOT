"""F1-F4 fixture shape + exact-number checks. plans/reports/plan.md §4.4,
plans/260816-0957-data-plane/phase-06-fixtures-and-eval.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from registry.specs import get_spec, wsum

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

FIXTURE_FILES = {
    "F1": ("f1_bundle_healthy.json", "AUTO"),
    "F2": ("f2_bundle_stale.json", "PROPOSE"),
    "F3": ("f3_bundle_broken.json", "INVESTIGATE"),
    "F4": ("f4_bundle_stuck.json", "INVESTIGATE"),
}


@pytest.mark.data_plane
@pytest.mark.parametrize("fixture_id", sorted(FIXTURE_FILES))
def test_fixture_is_valid_json_matching_payload_shape(fixture_id):
    filename, _ = FIXTURE_FILES[fixture_id]
    doc = json.loads((FIXTURES_DIR / filename).read_text())

    assert doc["fixture_id"] == fixture_id
    assert doc["scope"] == "irrigation_plan"
    assert doc["wsum"] == wsum("irrigation_plan") == 13
    assert isinstance(doc["readings"], list) and doc["readings"]

    for reading in doc["readings"]:
        spec = get_spec(reading["device"], reading["metric"])
        assert spec is not None, (
            f"{fixture_id}: unknown device.metric {reading['device']}.{reading['metric']}"
        )
        assert reading["unit"] == spec.unit
        assert reading["reading_status"] in ("FRESH", "STALE", "SUSPECT", "OFFLINE", "MISSING")


@pytest.mark.data_plane
@pytest.mark.parametrize("fixture_id", sorted(FIXTURE_FILES))
def test_fixture_expected_tier_matches_section_4_4(fixture_id):
    filename, expected_tier = FIXTURE_FILES[fixture_id]
    doc = json.loads((FIXTURES_DIR / filename).read_text())
    assert doc["expected"]["tier"] == expected_tier


def test_f1_all_fresh_no_rules_fired():
    doc = json.loads((FIXTURES_DIR / "f1_bundle_healthy.json").read_text())
    assert all(r["reading_status"] == "FRESH" for r in doc["readings"])
    assert doc["rules_fired"] == []
    assert doc["expected"]["dcs"] == 1.0


def test_f2_stale_freshness_values():
    doc = json.loads((FIXTURES_DIR / "f2_bundle_stale.json").read_text())
    by_device = {r["device"]: r for r in doc["readings"]}
    assert by_device["SOIL_01"]["freshness"] == pytest.approx(0.10, abs=1e-6)
    assert by_device["WEATHER_01"]["freshness"] == pytest.approx(0.25, abs=1e-6)
    assert doc["expected"]["dcs"] == pytest.approx(0.80, abs=0.01)


def test_f3_soil_offline_required_metric_caps_dcs():
    doc = json.loads((FIXTURES_DIR / "f3_bundle_broken.json").read_text())
    soil_readings = [r for r in doc["readings"] if r["device"] == "SOIL_01"]
    assert all(r["reading_status"] == "OFFLINE" for r in soil_readings)
    assert any(r["required"] for r in soil_readings)
    assert doc["expected"]["cap_applied"] == 0.40
    assert doc["expected"]["dcs"] == 0.40


def test_f4_stuck_sensor_still_capped_despite_fresh_age():
    doc = json.loads((FIXTURES_DIR / "f4_bundle_stuck.json").read_text())
    stuck = next(
        r for r in doc["readings"] if (r["device"], r["metric"]) == ("SOIL_01", "soil_moisture")
    )
    assert stuck["reading_status"] == "SUSPECT"
    assert "stuck_at" in stuck
    assert doc["expected"]["cap_applied"] == 0.40
    assert doc["expected"]["dcs"] == 0.40
