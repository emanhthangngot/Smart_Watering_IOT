"""Stable backward traversal over the M3 evidence graph."""

from __future__ import annotations

from collections import deque

from .edges import EdgeRelation, EvidenceGraph


def trace_to_readings(graph: EvidenceGraph, decision_id: str) -> tuple[str, ...]:
    if not graph.has_node(decision_id):
        return ()
    queue = deque([decision_id])
    visited = {decision_id}
    readings: set[str] = set()
    while queue:
        current = queue.popleft()
        for edge in graph.incoming(current):
            if edge.relation not in (EdgeRelation.SUPPORTS, EdgeRelation.DERIVED_FROM):
                continue
            source = edge.source
            if source.startswith("r_"):
                readings.add(source)
            if source not in visited:
                visited.add(source)
                queue.append(source)
    return tuple(sorted(readings))


__all__ = ["trace_to_readings"]
