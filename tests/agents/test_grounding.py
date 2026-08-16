import pytest

from graph.grounding import (
    DecisionEvidenceView,
    GroundingError,
    SemanticClaimMismatch,
    SensorClaim,
    UngroundedClaim,
    assert_grounded,
    run_grounded_narration,
    split_evidence_ref,
    validate_sensor_claim,
)

pytestmark = pytest.mark.agents


REF = "r_123e4567-e89b-42d3-a456-426614174000#level"


def test_membership_and_metric_qualified_ref() -> None:
    assert split_evidence_ref(REF)[1] == "level"
    assert_grounded([REF], [REF])
    with pytest.raises(UngroundedClaim) as error:
        assert_grounded([REF, "missing"], [REF])
    assert error.value.missing == ("missing",)


def test_split_evidence_ref_accepts_m1s_real_hash_based_reading_id() -> None:
    # ingest/normalize.py::_reading_id — "r_" + sha256(canonical)[:24], a
    # deterministic lowercase hex digest, not a random UUIDv4. See C8 note
    # in graph/grounding.py.
    ref = "r_9f1c2e4a7b3d5f60189c2ab4#tank_level"
    assert split_evidence_ref(ref) == ("r_9f1c2e4a7b3d5f60189c2ab4", "tank_level")


def test_split_evidence_ref_rejects_missing_metric_or_bad_charset() -> None:
    with pytest.raises(GroundingError):
        split_evidence_ref("r_9f1c2e4a7b3d5f60189c2ab4")
    with pytest.raises(GroundingError):
        split_evidence_ref("r_9f1c2e4a7b3d5f60189c2ab4#level\nmore")
    with pytest.raises(GroundingError):
        split_evidence_ref("not_r_prefixed#level")


def test_typed_claim_checks_semantics_and_version() -> None:
    evidence = DecisionEvidenceView(REF, "level", value=50, unit="%", source_state_version=3)
    validate_sensor_claim(
        SensorClaim(REF, "level", value=50, unit="%", source_state_version=3), evidence
    )
    with pytest.raises(SemanticClaimMismatch):
        validate_sensor_claim(
            SensorClaim(REF, "level", value=51, unit="%", source_state_version=3), evidence
        )
    with pytest.raises(SemanticClaimMismatch):
        validate_sensor_claim(
            SensorClaim(REF, "level", value=50, unit="%", source_state_version=4), evidence
        )
    with pytest.raises(GroundingError):
        validate_sensor_claim(
            SensorClaim(
                REF.replace("#level", "#flow_rate"),
                "level",
                value=50,
                unit="%",
                source_state_version=3,
            ),
            evidence,
        )


def test_narration_has_two_attempt_cap() -> None:
    calls = 0

    def narrate():
        nonlocal calls
        calls += 1
        return "bad"

    def validate(_):
        raise UngroundedClaim(["missing"])

    assert (
        run_grounded_narration(narrate, validate, lambda: "fallback", max_retries=9) == "fallback"
    )
    assert calls == 2
