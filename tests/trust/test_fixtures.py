from __future__ import annotations

import json
from pathlib import Path

import pytest

from trust.score import score_readings
from trust.tier import evaluate_tier

pytestmark = pytest.mark.trust

FIXTURES = Path(__file__).parents[2] / "fixtures"


@pytest.mark.parametrize(
    ("filename", "expected_tier"),
    [
        ("f1_bundle_healthy.json", "AUTO"),
        ("f2_bundle_stale.json", "PROPOSE"),
        ("f3_bundle_broken.json", "INVESTIGATE"),
        ("f4_bundle_stuck.json", "INVESTIGATE"),
    ],
)
def test_g2_fixtures_match_hand_computed_scores(filename: str, expected_tier: str) -> None:
    fixture = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    expected = fixture["expected"]
    snapshot = score_readings(
        fixture["readings"],
        fixture["scope"],
        fired_rules=fixture["rules_fired"],
    )

    assert snapshot.freshness == pytest.approx(expected["F"], abs=0.0001)
    assert snapshot.completeness == pytest.approx(expected["C"], abs=0.0001)
    assert snapshot.consistency == pytest.approx(expected["K"], abs=0.0001)
    assert snapshot.dcs == pytest.approx(expected["dcs"], abs=0.0001)
    assert snapshot.cap_applied == expected["cap_applied"]
    assert evaluate_tier(snapshot.dcs).tier == expected_tier
    if fixture["fixture_id"] == "F4":
        assert "stuck_at" in snapshot.rules_fired
    else:
        assert snapshot.rules_fired == tuple(expected["rules_fired"])
