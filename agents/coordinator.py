"""Deterministic routing over the intentionally lossy RouteSignal projection."""

from __future__ import annotations

from collections.abc import Iterable

from .messages import RouteDecision, RouteSignal
from .vocabulary import InteractionVerb


class RoutingError(ValueError):
    """Raised when a route cannot be determined safely."""


def route(signals: Iterable[RouteSignal], state_version: int) -> RouteDecision:
    ordered = tuple(sorted(signals, key=lambda signal: signal.signal_id))
    if not ordered:
        raise RoutingError("at least one route signal is required")
    if any(signal.source_state_version != state_version for signal in ordered):
        raise RoutingError("route signals must match the requested state version")
    if len({signal.source_state_version for signal in ordered}) != 1:
        raise RoutingError("mixed route signal versions are not usable")

    blocking = tuple(signal for signal in ordered if signal.blocking)
    if any(signal.verb is InteractionVerb.ESCALATE_TO_HUMAN for signal in blocking):
        return RouteDecision(
            "human", InteractionVerb.ESCALATE_TO_HUMAN, state_version, _ids(ordered)
        )
    if any(signal.verb is InteractionVerb.REJECT for signal in blocking) and any(
        signal.verb is InteractionVerb.ACCEPT for signal in ordered
    ):
        raise RoutingError("accept and blocking reject are an invalid route state")
    if any(signal.verb is InteractionVerb.REJECT for signal in blocking):
        return RouteDecision("planner", InteractionVerb.REVISE, state_version, _ids(ordered))
    if any(signal.verb is InteractionVerb.REQUEST_MORE_EVIDENCE for signal in ordered):
        return RouteDecision(
            "field_evidence", InteractionVerb.REQUEST_MORE_EVIDENCE, state_version, _ids(ordered)
        )
    if any(signal.verb is InteractionVerb.REVISE for signal in ordered):
        return RouteDecision("planner", InteractionVerb.REVISE, state_version, _ids(ordered))
    if all(signal.verb is InteractionVerb.ACCEPT for signal in ordered):
        return RouteDecision("planner", InteractionVerb.PROPOSE, state_version, _ids(ordered))
    raise RoutingError("conflicting route signals have no safe transition")


def _ids(signals: tuple[RouteSignal, ...]) -> tuple[str, ...]:
    return tuple(signal.signal_id for signal in signals)


__all__ = ["RoutingError", "route"]
