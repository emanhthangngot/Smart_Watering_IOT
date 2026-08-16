import pytest

from graph.edges import EdgeRelation, EvidenceEdge, EvidenceGraph
from graph.explain import trace_to_readings

pytestmark = pytest.mark.agents


def test_backward_trace_is_cycle_safe_stable_and_deduplicated() -> None:
    graph = EvidenceGraph()
    graph.add(EvidenceEdge("r_1", "diagnosis", EdgeRelation.SUPPORTS, "t1"))
    graph.add(EvidenceEdge("diagnosis", "plan", EdgeRelation.DERIVED_FROM, "t2"))
    graph.add(EvidenceEdge("r_2", "plan", EdgeRelation.SUPPORTS, "t3"))
    graph.add(EvidenceEdge("plan", "diagnosis", EdgeRelation.DERIVED_FROM, "t4"))
    graph.add(EvidenceEdge("r_1", "plan", EdgeRelation.SUPPORTS, "t5"))
    assert trace_to_readings(graph, "plan") == ("r_1", "r_2")
    assert trace_to_readings(graph, "missing") == ()
