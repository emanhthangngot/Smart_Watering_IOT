"""Outcome verification with an explicit observational mode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from contracts import Verification

ActuationTarget = Literal["none", "sim"]


def verify_outcome(
    *,
    actuation_target: ActuationTarget,
    pump_activity_observed: bool | None,
    evidence_usable: bool,
    expected_met: bool | None,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    window: str,
    evidence_refs: list[str] | None = None,
) -> Verification:
    if actuation_target not in {"none", "sim"}:
        raise ValueError(f"unsupported actuation target: {actuation_target!r}")
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    if not evidence_usable or not evidence_refs or any(not ref.strip() for ref in evidence_refs):
        result = "INCONCLUSIVE"
    elif actuation_target == "none" and pump_activity_observed is not True:
        result = "INCONCLUSIVE"
    elif expected_met is None:
        result = "INCONCLUSIVE"
    else:
        result = "PASS" if expected_met else "FAIL"
    return Verification(
        layer="OUTCOME",
        expected=dict(expected),
        observed=dict(observed),
        result=result,
        window=window,
        evidence_refs=evidence_refs or [],
    )
