"""Narrow MQTT expected-vs-actual predicates (§10.3), not a digital twin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trust._access import field, values


@dataclass(frozen=True)
class Divergence:
    metric: str
    expected: float
    observed: float | None
    result: str
    assumptionId: str
    delta: float | None
    trajectory: tuple[float, ...]

    @property
    def affectedAssumptionId(self) -> str:
        """Compatibility with the ExpectedOutcome contract field name."""
        return self.assumptionId


def evaluate(expected_outcome: Any, readings: Any) -> Divergence:
    """Evaluate one ExpectedOutcome while preserving its causal assumption ID."""
    metric = field(expected_outcome, "metric")
    predicate = field(expected_outcome, "predicate", "at_least")
    threshold = field(expected_outcome, "threshold")
    tolerance = field(expected_outcome, "tolerance", 0)
    assumption_id = field(
        expected_outcome,
        "affected_assumption_id",
        field(expected_outcome, "affectedAssumptionId", field(expected_outcome, "assumptionId")),
    )
    if not assumption_id:
        raise ValueError("ExpectedOutcome requires affected_assumption_id")
    series = values(readings, *str(metric).split(".", 1)) if "." in str(metric) else []
    trajectory = tuple(series)
    if not series or threshold is None:
        return Divergence(
            str(metric),
            float(threshold or 0),
            None,
            "INCONCLUSIVE",
            assumption_id,
            None,
            trajectory,
        )
    threshold, tolerance = float(threshold), float(tolerance or 0)
    if predicate in {"at_least", ">=", "min"}:
        observed = min(series)
        passed = observed >= threshold - tolerance
    elif predicate in {"at_most", "<=", "max"}:
        observed = max(series)
        passed = observed <= threshold + tolerance
    elif predicate in {"increase", "delta_at_least"}:
        observed = series[-1] - series[0] if len(series) >= 2 else None
        if observed is None:
            return Divergence(
                str(metric), threshold, None, "INCONCLUSIVE", assumption_id, None, trajectory
            )
        passed = observed >= threshold - tolerance
    elif predicate in {"decrease", "delta_at_most"}:
        observed = series[-1] - series[0] if len(series) >= 2 else None
        if observed is None:
            return Divergence(
                str(metric), threshold, None, "INCONCLUSIVE", assumption_id, None, trajectory
            )
        passed = observed <= threshold + tolerance
    else:
        observed = series[-1]
        passed = abs(observed - threshold) <= tolerance
    return Divergence(
        str(metric),
        threshold,
        observed,
        "PASS" if passed else "FAIL",
        assumption_id,
        observed - threshold,
        trajectory,
    )
