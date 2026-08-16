"""Validated in-memory evidence graph primitives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InvalidEdge(ValueError):
    """Raised when an edge does not contain a valid node or relation."""


class EdgeRelation(StrEnum):
    SUPPORTS = "supports"
    DERIVED_FROM = "derived_from"
    PRODUCED = "produced"
    VERIFIED_BY = "verified_by"
    INVALIDATES = "invalidates"


@dataclass(frozen=True, slots=True)
class EvidenceEdge:
    source: str
    destination: str
    relation: EdgeRelation
    trace_id: str

    def __post_init__(self) -> None:
        if not self.source or not self.destination or not self.trace_id:
            raise InvalidEdge("edge nodes and trace id are required")
        if not isinstance(self.relation, EdgeRelation):
            raise InvalidEdge("unknown edge relation")
        if self.relation in (
            EdgeRelation.SUPPORTS,
            EdgeRelation.DERIVED_FROM,
        ) and self.destination.startswith("r_"):
            raise InvalidEdge("backward evidence edges cannot point into a reading node")


class EvidenceGraph:
    def __init__(self) -> None:
        self._edges: set[EvidenceEdge] = set()

    def add(self, edge: EvidenceEdge) -> None:
        self._edges.add(edge)

    def edges(self) -> tuple[EvidenceEdge, ...]:
        return tuple(
            sorted(
                self._edges,
                key=lambda edge: (
                    edge.destination,
                    edge.source,
                    edge.relation.value,
                    edge.trace_id,
                ),
            )
        )

    def has_node(self, node_id: str) -> bool:
        return any(edge.source == node_id or edge.destination == node_id for edge in self._edges)

    def incoming(self, node_id: str) -> tuple[EvidenceEdge, ...]:
        return tuple(edge for edge in self.edges() if edge.destination == node_id)


__all__ = ["EdgeRelation", "EvidenceEdge", "EvidenceGraph", "InvalidEdge"]
