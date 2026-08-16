"""Device registry — the sole source of truth for unit, ttl_batches, per-scope
weight, and required flags for every (device, metric) pair.

Design reference: plans/reports/plan.md §3.6. Frozen at G0 alongside
contracts.py (plans/260816-0957-farmops-delivery/phase-02-contract-lock.md).

Read by: store/gen_ddl.py (schema generation), trust/ (freshness/weights),
eval/score_scenarios.py (segment scoring). No module hand-copies these
numbers — cut this file if a metric needs to change, nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCOPES: tuple[str, ...] = ("irrigation_plan", "session_check", "tank_quality")


@dataclass(frozen=True)
class MetricSpec:
    device_code: str
    metric: str
    unit: str
    ttl_batches: int
    weights: dict[str, int] = field(default_factory=dict)
    required_scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def key(self) -> tuple[str, str]:
        return (self.device_code, self.metric)


# One row per device.metric in §3.6, numbers copied verbatim from the table.
SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        device_code="SOIL_01",
        metric="soil_moisture",
        unit="%",
        ttl_batches=3,
        weights={"irrigation_plan": 3, "session_check": 3},
        required_scopes=frozenset({"irrigation_plan", "session_check"}),
    ),
    MetricSpec(
        device_code="SOIL_01",
        metric="temperature",
        unit="°C",
        ttl_batches=3,
        weights={"irrigation_plan": 1},
    ),
    MetricSpec(
        device_code="WEATHER_01",
        metric="temperature",
        unit="°C",
        ttl_batches=6,
        weights={"irrigation_plan": 1},
    ),
    MetricSpec(
        device_code="WEATHER_01",
        metric="humidity",
        unit="%",
        ttl_batches=6,
        weights={"irrigation_plan": 2},
    ),
    MetricSpec(
        device_code="PUMP_01",
        metric="flow_rate",
        unit="L/min",
        ttl_batches=2,
        weights={"irrigation_plan": 2, "session_check": 3},
        required_scopes=frozenset({"session_check"}),
    ),
    MetricSpec(
        device_code="PUMP_01",
        metric="power",
        unit="W",
        ttl_batches=2,
        weights={"session_check": 1},
    ),
    MetricSpec(
        device_code="PH_01",
        metric="ph",
        unit="pH",
        ttl_batches=9,
        weights={"tank_quality": 3},
        required_scopes=frozenset({"tank_quality"}),
    ),
    MetricSpec(
        device_code="TANK_01",
        metric="level",
        unit="%",
        ttl_batches=3,
        weights={"irrigation_plan": 3, "session_check": 2, "tank_quality": 2},
        required_scopes=frozenset({"irrigation_plan"}),
    ),
    MetricSpec(
        device_code="SUN_01",
        metric="lux",
        unit="lx",
        ttl_batches=3,
        weights={"irrigation_plan": 1},
    ),
)

_BY_KEY: dict[tuple[str, str], MetricSpec] = {spec.key: spec for spec in SPECS}

DEVICES: tuple[str, ...] = tuple(dict.fromkeys(spec.device_code for spec in SPECS))


def get_spec(device_code: str, metric: str) -> MetricSpec | None:
    """Return the registry entry for (device_code, metric), or None if unknown."""
    return _BY_KEY.get((device_code, metric))


def metrics_for_device(device_code: str) -> tuple[MetricSpec, ...]:
    return tuple(spec for spec in SPECS if spec.device_code == device_code)


def wsum(scope: str) -> int:
    """Sum of weights for every metric that participates in `scope`."""
    return sum(spec.weights.get(scope, 0) for spec in SPECS)


def is_required(device_code: str, metric: str, scope: str) -> bool:
    spec = get_spec(device_code, metric)
    return spec is not None and scope in spec.required_scopes


def required_specs(scope: str) -> tuple[MetricSpec, ...]:
    return tuple(spec for spec in SPECS if scope in spec.required_scopes)
