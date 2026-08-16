"""Allocator-first orchestration with optional narrative-only phrasing."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from graph.grounding import (
    DecisionEvidenceView,
    GroundingError,
    SensorClaim,
    assert_grounded,
    run_grounded_narration,
    validate_sensor_claim,
)

from .allocator import AllocationRequest, AllocationResult, allocate


@dataclass(frozen=True, slots=True)
class NarrativeFields:
    summary: str
    reasons: tuple[str, ...] = ()
    claims: tuple[SensorClaim, ...] = ()


class PlanNarrator(Protocol):
    def narrate(
        self, allocation: AllocationResult, grounded_facts: Sequence[Mapping[str, object]]
    ) -> NarrativeFields:
        """Return prose only; quantitative allocation remains authoritative."""


def _deterministic_narrative(result: AllocationResult) -> str:
    if result.slices:
        return f"Allocated {len(result.slices)} irrigation slice(s) deterministically."
    return "No irrigation slice was accepted by the deterministic constraints."


def plan(
    request: AllocationRequest,
    *,
    narrator: PlanNarrator | None = None,
    grounded_facts: Sequence[Mapping[str, object]] = (),
) -> AllocationResult:
    result = allocate(request)
    fallback = _deterministic_narrative(result)
    if narrator is None:
        return AllocationResult(
            result.source_state_version, result.slices, result.reasons, fallback
        )
    evidence_by_ref = {
        fact.ref: fact for fact in grounded_facts if isinstance(fact, DecisionEvidenceView)
    }

    def validate(narrative: object) -> None:
        if not isinstance(narrative, NarrativeFields):
            raise GroundingError("narrator must return NarrativeFields")
        refs = [claim.ref for claim in narrative.claims]
        assert_grounded(refs, evidence_by_ref)
        for claim in narrative.claims:
            evidence = evidence_by_ref.get(claim.ref)
            if evidence is None:
                raise GroundingError("claim has no typed decision-time evidence")
            validate_sensor_claim(claim, evidence)
        numeric_tokens = re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?", narrative.summary)
        claimed_values = {
            Decimal(str(claim.value))
            for claim in narrative.claims
            if claim.value is not None and _is_decimal(str(claim.value))
        }
        if any(Decimal(token) not in claimed_values for token in numeric_tokens):
            raise GroundingError("numeric narrative requires a typed grounded claim")
        status_words = {
            "LOW",
            "HIGH",
            "OK",
            "STALE",
            "FRESH",
            "PASS",
            "FAIL",
            "INCONCLUSIVE",
            "INVALID",
            "VALID",
            "ON",
            "OFF",
        }
        mentioned_statuses = (
            set(re.findall(r"\b[A-Z][A-Z_]+\b", narrative.summary.upper())) & status_words
        )
        claimed_statuses = {
            str(claim.status).upper() for claim in narrative.claims if claim.status is not None
        }
        if not mentioned_statuses <= claimed_statuses:
            raise GroundingError("status narrative requires a typed grounded claim")

    try:
        narrative = run_grounded_narration(
            lambda: narrator.narrate(result, grounded_facts),
            validate,
            lambda: NarrativeFields(fallback),
        )
        return AllocationResult(
            result.source_state_version, result.slices, result.reasons, narrative.summary
        )
    except (ConnectionError, GroundingError, TimeoutError):
        return AllocationResult(
            result.source_state_version, result.slices, result.reasons, fallback
        )


__all__ = ["NarrativeFields", "PlanNarrator", "plan"]


def _is_decimal(value: str) -> bool:
    try:
        Decimal(value)
    except InvalidOperation:
        return False
    return True
