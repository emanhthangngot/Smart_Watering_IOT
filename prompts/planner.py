"""Restricted planner prompt boundary; values are data, never instructions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from decimal import Decimal

from agents.allocator import AllocationResult
from graph.grounding import DecisionEvidenceView
from worldstate.llm_slice import ForbiddenStateKey, assert_no_forbidden_keys


class PromptBoundaryError(ValueError):
    """Raised when unapproved state is offered to the narrative boundary."""


_FACT_KEYS = frozenset(
    {
        "ref",
        "metric",
        "value",
        "status",
        "unit",
        "source_state_version",
        "trust_eligible",
        "freshness_eligible",
        "observed_at",
    }
)


def _safe_facts(
    grounded_facts: Sequence[Mapping[str, object] | DecisionEvidenceView],
) -> list[dict[str, object]]:
    safe: list[dict[str, object]] = []
    for fact in grounded_facts:
        if isinstance(fact, DecisionEvidenceView):
            fact = asdict(fact)
        elif not isinstance(fact, Mapping):
            raise PromptBoundaryError("grounded fact must be a mapping or DecisionEvidenceView")
        try:
            assert_no_forbidden_keys(fact)
        except ForbiddenStateKey as exc:
            raise PromptBoundaryError(f"forbidden grounded fact field: {exc}") from exc
        unknown = set(fact) - _FACT_KEYS
        if unknown:
            raise PromptBoundaryError(
                f"unapproved grounded fact fields: {', '.join(sorted(unknown))}"
            )
        normalized: dict[str, object] = {}
        for key in sorted(fact):
            value = fact[key]
            if isinstance(value, Decimal):
                value = str(value)
            if value is not None and not isinstance(value, (bool, int, float, str)):
                raise PromptBoundaryError(f"grounded fact field {key!r} must be scalar")
            normalized[key] = value
        safe.append(normalized)
    return safe


def build_planner_prompt(
    allocation: AllocationResult,
    grounded_facts: Sequence[Mapping[str, object] | DecisionEvidenceView],
) -> str:
    payload = {
        "allocation": [
            {
                "candidate_id": item.candidate_id,
                "pump_id": item.pump_id,
                "start": item.window.start.isoformat(),
                "end": item.window.end.isoformat(),
                "duration_minutes": str(item.duration_minutes),
                "drawdown_pct": str(item.drawdown_pct),
            }
            for item in allocation.slices
        ],
        "reasons": [{"code": item.code, "message": item.message} for item in allocation.reasons],
        "grounded_facts": _safe_facts(grounded_facts),
    }
    return "Narrate the following structured data without changing it:\n" + json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


__all__ = ["PromptBoundaryError", "build_planner_prompt"]
