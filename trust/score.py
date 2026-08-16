"""Per-scope deterministic confidence scoring (DCS, §4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from trust._access import field
from trust.freshness import freshness as calculate_freshness
from trust.rules import stuck_at
from trust.rules.registry import hard_fails, soft_rules
from trust.states import ReadingState, assign_state, is_usable

DCS_POLICY_VERSION = "1"


@dataclass(frozen=True)
class ScoreSnapshot:
    scope: str
    freshness: float
    completeness: float
    consistency: float
    dcs: float
    cap_applied: float | None
    rules_fired: tuple[str, ...]
    blocked_required_metrics: tuple[str, ...]
    dcsPolicyVersion: str = DCS_POLICY_VERSION

    def payload(self) -> dict[str, Any]:
        result = asdict(self)
        result.update(
            {
                "F": self.freshness,
                "C": self.completeness,
                "K": self.consistency,
                "actionAllowed": not self.blocked_required_metrics,
            }
        )
        return result


def _spec_value(spec: Any, name: str, default: Any = None) -> Any:
    return field(spec, name, default)


def _scope_metrics(scope: str, specs: Mapping[str, Any]) -> dict[str, tuple[float, bool]]:
    """Accept the frozen registry's eventual shape or an explicit test mapping."""
    selected = specs.get(scope, specs)
    if not isinstance(selected, Mapping):
        return {}
    result: dict[str, tuple[float, bool]] = {}
    for key, spec in selected.items():
        weights = _spec_value(spec, "weights", _spec_value(spec, "scope_weights", {}))
        scoped_weight = weights.get(scope, 0) if isinstance(weights, Mapping) else 0
        weight = _spec_value(spec, "weight", _spec_value(spec, scope, scoped_weight))
        required = _spec_value(spec, "required", False)
        if isinstance(required, (list, tuple, set)):
            required = scope in required
        elif isinstance(required, str):
            required = required == scope
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        if weight > 0:
            normalized_key = (
                f"{key[0]}.{key[1]}" if isinstance(key, tuple) and len(key) == 2 else str(key)
            )
            result[normalized_key] = (weight, bool(required))
    return result


def apply_hard_fails(
    bundle: Mapping[str, Any], windows: Any
) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    """Return a copied bundle whose affected readings are SUSPECT."""
    result: dict[str, dict[str, Any]] = {}
    for key, value in bundle.items():
        if isinstance(value, Mapping):
            result[key] = dict(value)
            continue
        item = {"value": field(value, "value", value)}
        for name in ("source_status", "status", "state", "freshness"):
            attribute = field(value, name)
            if attribute is not None:
                item[name] = attribute
        result[key] = item
    fired: set[str] = set()
    stuck = stuck_at.affected_keys(bundle, windows)
    hard_rule_map = hard_fails()
    for key, item in result.items():
        individual = {key: item}
        for name, predicate in hard_rule_map.items():
            if predicate is not stuck_at.rule and predicate(individual, windows):
                item["state"] = ReadingState.SUSPECT
                fired.add(name)
        if key in stuck:
            item["state"] = ReadingState.SUSPECT
            fired.add("stuck_at")
    return result, tuple(sorted(fired))


def score_scope(
    bundle: Mapping[str, Any],
    windows: Any,
    scope: str,
    specs: Mapping[str, Any],
    *,
    ages: Mapping[str, float] | None = None,
    ttls: Mapping[str, float] | None = None,
) -> ScoreSnapshot:
    """Score one scope. The caller supplies M1's frozen registry mapping."""
    metrics = _scope_metrics(scope, specs)
    prepared, hard_fired = apply_hard_fails(bundle, windows)
    total_weight = sum(weight for weight, _ in metrics.values())
    if total_weight <= 0:
        return ScoreSnapshot(scope, 0.0, 0.0, 0.0, 0.0, 0.40, hard_fired, ())
    ages, ttls = ages or {}, ttls or {}
    fresh_total = complete_total = 0.0
    required_unusable = False
    blocked_required: list[str] = []
    for key, (weight, required) in metrics.items():
        item = prepared.get(key)
        state = field(item, "state") if item is not None else ReadingState.MISSING
        if state is None:
            state = assign_state(item, age=ages.get(key, 0), ttl=ttls.get(key, 1))
        try:
            state = ReadingState(str(state))
        except ValueError:
            state = ReadingState.MISSING
        explicit_freshness = field(item, "freshness")
        if not is_usable(state):
            metric_freshness = 0.0
        elif explicit_freshness is not None:
            try:
                metric_freshness = float(explicit_freshness)
            except (TypeError, ValueError):
                metric_freshness = 0.0
        elif key in ages and key in ttls:
            metric_freshness = calculate_freshness(ages[key], ttls[key])
        else:
            metric_freshness = 1.0 if state is ReadingState.FRESH else 0.0
        metric_freshness = (
            max(0.0, min(1.0, metric_freshness)) if isfinite(metric_freshness) else 0.0
        )
        if is_usable(state):
            fresh_total += weight * metric_freshness
            complete_total += weight
        if required and state in {
            ReadingState.STALE,
            ReadingState.SUSPECT,
            ReadingState.OFFLINE,
            ReadingState.MISSING,
        }:
            blocked_required.append(key)
        if required and (
            state in {ReadingState.SUSPECT, ReadingState.OFFLINE, ReadingState.MISSING}
            or metric_freshness == 0
        ):
            required_unusable = True
    soft_fired = tuple(
        name for name, predicate in soft_rules().items() if predicate(prepared, windows)
    )
    penalties = []
    for name in soft_fired:
        module = __import__(f"trust.rules.{name}", fromlist=["PENALTY"])
        penalties.append(float(module.PENALTY))
    consistency = max(0.0, 1.0 - sum(penalties))
    raw = (
        0.45 * fresh_total / total_weight
        + 0.35 * complete_total / total_weight
        + 0.20 * consistency
    )
    cap = 0.40 if required_unusable else 0.55 if consistency < 0.50 else None
    return ScoreSnapshot(
        scope,
        fresh_total / total_weight,
        complete_total / total_weight,
        consistency,
        min(raw, cap) if cap is not None else raw,
        cap,
        tuple(sorted(set(hard_fired + soft_fired))),
        tuple(sorted(blocked_required)),
    )
