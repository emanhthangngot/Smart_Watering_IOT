import pytest

from graph.edges import EdgeRelation, EvidenceEdge, EvidenceGraph, InvalidEdge

pytestmark = pytest.mark.agents


def test_relation_set_and_exact_duplicate_deduplication() -> None:
    assert {item.value for item in EdgeRelation} == {
        "supports",
        "derived_from",
        "produced",
        "verified_by",
        "invalidates",
    }
    graph = EvidenceGraph()
    edge = EvidenceEdge("r_a", "decision", EdgeRelation.SUPPORTS, "trace-1")
    graph.add(edge)
    graph.add(edge)
    assert graph.edges() == (edge,)


def test_invalid_edge_fails_closed() -> None:
    with pytest.raises(InvalidEdge):
        EvidenceEdge("", "decision", EdgeRelation.SUPPORTS, "trace")
    with pytest.raises(InvalidEdge):
        EvidenceEdge("r_a", "decision", "bad", "trace")
    with pytest.raises(InvalidEdge):
        EvidenceEdge("plan", "r_a", EdgeRelation.SUPPORTS, "trace")
