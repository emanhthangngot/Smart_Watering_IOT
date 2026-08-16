"""Pure structural and semantic grounding checks for decision-time evidence."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class GroundingError(ValueError):
    """Base error for a claim that cannot be grounded."""


class UngroundedClaim(GroundingError):
    """Raised when one or more cited references are unavailable."""

    def __init__(self, missing: Iterable[str]) -> None:
        self.missing = tuple(sorted(set(missing)))
        super().__init__(f"missing evidence refs: {', '.join(self.missing)}")


class SemanticClaimMismatch(GroundingError):
    """Raised when a cited evidence record does not support the claim."""


_UUID_REF = re.compile(
    r"^r_[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}#[A-Za-z0-9_]+$"
)


def split_evidence_ref(ref: str) -> tuple[str, str]:
    if not isinstance(ref, str) or not _UUID_REF.fullmatch(ref):
        raise GroundingError("evidence ref must be r_<uuidv4>#<metric>")
    reading_id, metric = ref.split("#", 1)
    return reading_id, metric


def assert_grounded(requested: Collection[str], available: Collection[str]) -> None:
    available_set = set(available)
    missing = sorted(set(requested) - available_set)
    if missing:
        raise UngroundedClaim(missing)


@dataclass(frozen=True, slots=True)
class DecisionEvidenceView:
    ref: str
    metric: str
    value: Decimal | float | int | None = None
    status: str | None = None
    unit: str = ""
    source_state_version: int = 0
    trust_eligible: bool = True
    freshness_eligible: bool = True
    observed_at: str = ""


@dataclass(frozen=True, slots=True)
class SensorClaim:
    ref: str
    metric: str
    value: Decimal | float | int | None = None
    status: str | None = None
    unit: str = ""
    source_state_version: int = 0


def _number(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SemanticClaimMismatch("numeric claim is not finite") from exc
    if not number.is_finite():
        raise SemanticClaimMismatch("numeric claim is not finite")
    return number


def validate_sensor_claim(claim: SensorClaim, evidence: DecisionEvidenceView) -> None:
    _, ref_metric = split_evidence_ref(claim.ref)
    _, evidence_metric = split_evidence_ref(evidence.ref)
    if ref_metric != claim.metric or evidence_metric != evidence.metric:
        raise SemanticClaimMismatch("reference metric suffix mismatch")
    if claim.ref != evidence.ref or claim.metric != evidence.metric:
        raise SemanticClaimMismatch("reference or metric mismatch")
    if claim.unit != evidence.unit or claim.source_state_version != evidence.source_state_version:
        raise SemanticClaimMismatch("unit or source state version mismatch")
    if not evidence.trust_eligible or not evidence.freshness_eligible:
        raise SemanticClaimMismatch("evidence is not eligible at decision time")
    if claim.value is not None:
        if evidence.value is None or _number(claim.value) != _number(evidence.value):
            raise SemanticClaimMismatch("numeric value mismatch")
    if claim.status is not None and claim.status != evidence.status:
        raise SemanticClaimMismatch("status mismatch")
    if claim.value is None and claim.status is None:
        raise SemanticClaimMismatch("claim has no typed value or status")


def run_grounded_narration(
    narrate: Callable[[], Any],
    validate: Callable[[Any], None],
    fallback: Callable[[], Any] | Any,
    *,
    max_retries: int = 2,
) -> Any:
    attempts = min(max(0, max_retries), 2)
    for _ in range(attempts):
        try:
            candidate = narrate()
            validate(candidate)
            return candidate
        except GroundingError:
            continue
    return fallback() if callable(fallback) else fallback


__all__ = [
    "DecisionEvidenceView",
    "GroundingError",
    "SemanticClaimMismatch",
    "SensorClaim",
    "UngroundedClaim",
    "assert_grounded",
    "run_grounded_narration",
    "split_evidence_ref",
    "validate_sensor_claim",
]
