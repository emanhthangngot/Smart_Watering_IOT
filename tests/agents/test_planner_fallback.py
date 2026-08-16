import pytest

from agents.allocator import AllocationCandidate, AllocationRequest, TimeWindow
from agents.planner import NarrativeFields, plan
from graph.grounding import DecisionEvidenceView, SensorClaim

pytestmark = pytest.mark.agents


def request() -> AllocationRequest:
    from datetime import datetime, timedelta

    start = datetime(2026, 8, 16, 1)
    return AllocationRequest(
        3,
        (
            AllocationCandidate(
                "a", 1, "P1", 5, 2, TimeWindow(start, start + timedelta(minutes=10)), 60, 20
            ),
        ),
        5,
        10,
        (TimeWindow(start, start + timedelta(minutes=30)),),
        resource_state_version=3,
        trust_state_version=3,
    )


class FailingNarrator:
    def narrate(self, allocation, grounded_facts):
        raise TimeoutError


class MutatingNarrator:
    def narrate(self, allocation, grounded_facts):
        return NarrativeFields("changed number 999")


class ContradictoryNarrator:
    def narrate(self, allocation, grounded_facts):
        evidence = grounded_facts[0]
        return NarrativeFields(
            "Tank is 999% full",
            claims=(
                SensorClaim(
                    evidence.ref,
                    evidence.metric,
                    value=50,
                    unit="%",
                    source_state_version=3,
                ),
            ),
        )


def test_provider_failure_keeps_deterministic_quantitative_result() -> None:
    result = plan(request(), narrator=FailingNarrator())
    assert len(result.slices) == 1
    assert "deterministically" in result.narrative


def test_narrator_cannot_change_quantitative_result() -> None:
    result = plan(request(), narrator=MutatingNarrator())
    assert result.slices[0].drawdown_pct == 2
    assert "deterministically" in result.narrative


def test_contradictory_typed_narrative_falls_back() -> None:
    ref = "r_123e4567-e89b-42d3-a456-426614174000#level"
    evidence = DecisionEvidenceView(ref, "level", value=50, unit="%", source_state_version=3)
    result = plan(request(), narrator=ContradictoryNarrator(), grounded_facts=(evidence,))
    assert "deterministically" in result.narrative
