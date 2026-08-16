"""Pure, advisory resource policy. M4 performs the final atomic reservation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from .messages import ResourceAssessment, ResourceInput


class ResourceInputError(ValueError):
    """Raised for malformed policy inputs that cannot be evaluated safely."""


def _decimal(value: Decimal | float | int | None, name: str) -> Decimal:
    if value is None:
        raise ResourceInputError(f"missing {name}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ResourceInputError(f"invalid {name}") from exc
    if not result.is_finite():
        raise ResourceInputError(f"invalid {name}")
    return result


def evaluate_resource(resource: ResourceInput) -> ResourceAssessment:
    if resource.source_state_version is None:
        return ResourceAssessment(
            False,
            True,
            True,
            "REQUEST_MORE_EVIDENCE: source state version is missing",
            None,
            None,
        )
    required = (
        (resource.level_pct, "level_pct"),
        (resource.safe_reserve_pct, "safe_reserve_pct"),
        (resource.active_reserved_drawdown_pct, "active_reserved_drawdown_pct"),
        (resource.requested_drawdown_pct, "requested_drawdown_pct"),
    )
    if any(value is None for value, _ in required):
        return ResourceAssessment(
            accepted=False,
            blocking=True,
            needs_more_evidence=True,
            reason="REQUEST_MORE_EVIDENCE: missing resource fact",
            available_drawdown_pct=None,
            source_state_version=resource.source_state_version,
        )
    if not resource.farm_day or not resource.timezone or resource.ledger_as_of is None:
        return ResourceAssessment(
            False,
            True,
            True,
            "REQUEST_MORE_EVIDENCE: missing farm-day, timezone, or ledger timestamp",
            None,
            resource.source_state_version,
        )
    if resource.now is None:
        return ResourceAssessment(
            False,
            True,
            True,
            "REQUEST_MORE_EVIDENCE: ledger freshness clock is missing",
            None,
            resource.source_state_version,
        )
    try:
        age = resource.now - resource.ledger_as_of
    except TypeError:
        return ResourceAssessment(
            False,
            True,
            True,
            "REQUEST_MORE_EVIDENCE: now and ledger_as_of are not comparable",
            None,
            resource.source_state_version,
        )
    if age < timedelta(0) or age.total_seconds() > resource.ledger_max_age_seconds:
        return ResourceAssessment(
            False,
            True,
            True,
            "REQUEST_MORE_EVIDENCE: ledger is stale",
            None,
            resource.source_state_version,
        )
    try:
        level = _decimal(resource.level_pct, "level_pct")
        reserve = _decimal(resource.safe_reserve_pct, "safe_reserve_pct")
        active = _decimal(resource.active_reserved_drawdown_pct, "active_reserved_drawdown_pct")
        requested = _decimal(resource.requested_drawdown_pct, "requested_drawdown_pct")
    except ResourceInputError as exc:
        return ResourceAssessment(
            False, True, True, f"REQUEST_MORE_EVIDENCE: {exc}", None, resource.source_state_version
        )

    available = max(Decimal(0), level - reserve)
    if resource.schedule_conflicts:
        return ResourceAssessment(
            False,
            True,
            False,
            "REJECT: schedule conflict",
            available,
            resource.source_state_version,
        )
    if active < 0 or requested < 0 or active + requested > available:
        return ResourceAssessment(
            False,
            True,
            False,
            "REJECT: active reservation plus request exceeds available drawdown",
            available,
            resource.source_state_version,
        )
    return ResourceAssessment(
        True,
        False,
        False,
        "ACCEPT: advisory resource budget is available",
        available,
        resource.source_state_version,
    )


__all__ = ["ResourceInputError", "evaluate_resource"]
