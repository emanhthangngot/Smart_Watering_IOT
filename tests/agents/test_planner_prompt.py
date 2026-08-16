import pytest

from agents.allocator import AllocationResult
from graph.grounding import DecisionEvidenceView
from prompts.planner import PromptBoundaryError, build_planner_prompt

pytestmark = pytest.mark.agents


def test_prompt_serializes_grounded_text_as_data() -> None:
    prompt = build_planner_prompt(
        AllocationResult(1, (), ()), ({"metric": "level", "value": 50, "unit": "%"},)
    )
    assert '"metric":"level"' in prompt
    assert "Narrate the following structured data" in prompt


def test_prompt_rejects_unapproved_state_fields() -> None:
    with pytest.raises(PromptBoundaryError):
        build_planner_prompt(AllocationResult(1, (), ()), ({"scenario": "NORMAL"},))


def test_prompt_rejects_nested_credential_shapes_and_accepts_typed_view() -> None:
    with pytest.raises(PromptBoundaryError):
        build_planner_prompt(AllocationResult(1, (), ()), ({"value": {"token": "secret"}},))
    prompt = build_planner_prompt(
        AllocationResult(1, (), ()),
        (
            DecisionEvidenceView(
                "r_123e4567-e89b-42d3-a456-426614174000#level", "level", 50, unit="%"
            ),
        ),
    )
    assert '"source_state_version":0' in prompt
