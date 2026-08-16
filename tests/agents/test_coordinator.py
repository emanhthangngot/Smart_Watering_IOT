import pytest

from agents.coordinator import RoutingError, route
from agents.messages import RouteSignal
from agents.vocabulary import InteractionVerb

pytestmark = pytest.mark.agents


def signal(identifier: str, verb: InteractionVerb, blocking: bool = False) -> RouteSignal:
    return RouteSignal(identifier, "diagnosis", verb, blocking, 4)


@pytest.mark.parametrize(
    ("verb", "blocking", "participant", "event"),
    [
        (InteractionVerb.ACCEPT, False, "planner", InteractionVerb.PROPOSE),
        (InteractionVerb.REVISE, False, "planner", InteractionVerb.REVISE),
        (
            InteractionVerb.REQUEST_MORE_EVIDENCE,
            False,
            "field_evidence",
            InteractionVerb.REQUEST_MORE_EVIDENCE,
        ),
        (InteractionVerb.REJECT, True, "planner", InteractionVerb.REVISE),
        (InteractionVerb.ESCALATE_TO_HUMAN, True, "human", InteractionVerb.ESCALATE_TO_HUMAN),
    ],
)
def test_visible_route_table(verb, blocking, participant, event) -> None:
    decision = route([signal("s1", verb, blocking)], 4)
    assert (decision.next_participant, decision.event, decision.source_state_version) == (
        participant,
        event,
        4,
    )


def test_mixed_versions_and_ambiguous_signals_fail_closed() -> None:
    with pytest.raises(RoutingError):
        route(
            [
                signal("a", InteractionVerb.ACCEPT),
                RouteSignal("b", "resource", InteractionVerb.ACCEPT, False, 5),
            ],
            4,
        )
    with pytest.raises(RoutingError):
        route([signal("a", InteractionVerb.ACCEPT), signal("b", InteractionVerb.PROPOSE)], 4)
    with pytest.raises(RoutingError):
        route([signal("a", InteractionVerb.ACCEPT), signal("b", InteractionVerb.REJECT, True)], 4)
