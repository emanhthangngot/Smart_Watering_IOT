"""Per-scope deterministic confidence scoring (DCS, §4.2)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from trust._access import field
from trust.freshness import freshness as calculate_freshness
from trust.rules import stuck_at
from trust.rules.registry import hard_fails, soft_rules
from trust.states import ReadingState, assign_state, is_usable

DCS_POLICY_VERSION = 1


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
    dcsPolicyVersion: int = DCS_POLICY_VERSION

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


def _scope_metrics(scope: str, specs: Any) -> dict[str, tuple[float, bool]]:
    """Normalize M1's frozen MetricSpec tuple or an explicit mapping."""
    selected = specs.get(scope, specs) if isinstance(specs, Mapping) else specs
    if not isinstance(selected, Mapping) and not isinstance(selected, Iterable):
        return {}
    result: dict[str, tuple[float, bool]] = {}
    entries = (
        selected.items()
        if isinstance(selected, Mapping)
        else ((field(spec, "key"), spec) for spec in selected)
    )
    for key, spec in entries:
        weights = _spec_value(spec, "weights", _spec_value(spec, "scope_weights", {}))
        scoped_weight = weights.get(scope, 0) if isinstance(weights, Mapping) else 0
        weight = _spec_value(spec, "weight", _spec_value(spec, scope, scoped_weight))
        required = _spec_value(spec, "required", _spec_value(spec, "required_scopes", False))
        if isinstance(required, (list, tuple, set, frozenset)):
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
    specs: Any = None,
    *,
    ages: Mapping[str, float] | None = None,
    ttls: Mapping[str, float] | None = None,
    fired_rules: Iterable[str] = (),
) -> ScoreSnapshot:
    """Score one scope against M1's frozen registry unless specs are supplied."""
    if specs is None:
        from registry.specs import SPECS

        specs = SPECS
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
    hard_rule_names = set(hard_fails())
    soft_rule_map = soft_rules()
    evaluated_soft = {
        name for name, predicate in soft_rule_map.items() if predicate(prepared, windows)
    }
    supplied_hard = {name for name in fired_rules if name in hard_rule_names}
    supplied_soft = {name for name in fired_rules if name in soft_rule_map}
    soft_fired = tuple(sorted(evaluated_soft | supplied_soft))
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
        tuple(sorted(set(hard_fired + tuple(supplied_hard) + soft_fired))),
        tuple(sorted(blocked_required)),
    )


def readings_to_bundle(readings: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Adapt normalized/fixture readings to the trust engine's keyed bundle."""
    bundle: dict[str, dict[str, Any]] = {}
    for item in readings:
        device = field(item, "device", field(item, "device_code"))
        metric = field(item, "metric")
        if not device or not metric:
            continue
        key = f"{device}.{metric}"
        bundle[key] = {
            "value": field(item, "value"),
            "source_status": field(item, "source_status", "ok"),
            "state": field(item, "state", field(item, "reading_status")),
            "freshness": field(item, "freshness"),
        }
    return bundle


def score_readings(
    readings: Iterable[Any],
    scope: str,
    *,
    windows: Any = None,
    specs: Any = None,
    fired_rules: Iterable[str] = (),
    ages: Mapping[str, float] | None = None,
    ttls: Mapping[str, float] | None = None,
) -> ScoreSnapshot:
    """Score normalized readings or an M1 fixture without copying registry data."""
    readings = tuple(readings)
    declared_rules = set(fired_rules)
    if any(field(item, "stuck_at") is not None for item in readings):
        declared_rules.add("stuck_at")
    return score_scope(
        readings_to_bundle(readings),
        windows or {},
        scope,
        specs,
        fired_rules=declared_rules,
        ages=ages,
        ttls=ttls,
    )
