"""Deterministic water-balance evidence, never an action or an LLM call."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any

from trust._access import delta, val
from trust.policy import CHANGE_EPSILON, FLOW_MIN, POWER_HIGH

EPSILON = CHANGE_EPSILON


@dataclass(frozen=True)
class WaterEvidence:
    diagnosis: str
    values: dict[str, float]
    advisory: bool = False


@dataclass(frozen=True)
class RatioBaseline:
    mean: float
    stddev: float
    samples: tuple[float, ...]
    warmup_complete: bool


def fit_ratio_baseline(
    sessions: list[tuple[float, float]], elapsed_seconds: float = 0
) -> RatioBaseline:
    """Fit |tank decline|/soil rise after 2 sessions or a 10-minute warm-up."""
    ratios = tuple(
        abs(tank_drop) / soil_rise for tank_drop, soil_rise in sessions if soil_rise > EPSILON
    )
    return RatioBaseline(
        mean(ratios) if ratios else 0.0,
        pstdev(ratios) if len(ratios) > 1 else 0.0,
        ratios,
        len(ratios) >= 2 or (elapsed_seconds >= 600 and bool(ratios)),
    )


def pipe_leak(bundle: Any, windows: Any) -> WaterEvidence | None:
    flow, tank, soil = (
        val(bundle, "PUMP_01", "flow_rate"),
        delta(windows, "TANK_01", "level"),
        delta(windows, "SOIL_01", "soil_moisture"),
    )
    if (
        flow is not None
        and tank is not None
        and soil is not None
        and flow > FLOW_MIN
        and tank < -EPSILON
        and soil <= EPSILON
    ):
        return WaterEvidence("pipe_leak", {"flow": flow, "tank_delta": tank, "soil_delta": soil})
    return None


def flow_tank_mismatch(bundle: Any, windows: Any) -> WaterEvidence | None:
    flow, tank = val(bundle, "PUMP_01", "flow_rate"), delta(windows, "TANK_01", "level")
    if flow is not None and tank is not None and flow > FLOW_MIN and abs(tank) <= EPSILON:
        return WaterEvidence("flow_tank_mismatch", {"flow": flow, "tank_delta": tank})
    return None


def dry_run_or_clogged_filter(bundle: Any, windows: Any) -> WaterEvidence | None:
    del windows
    power, flow = val(bundle, "PUMP_01", "power"), val(bundle, "PUMP_01", "flow_rate")
    if power is not None and flow is not None and power > POWER_HIGH and flow <= EPSILON:
        return WaterEvidence("dry_run_or_clogged_filter", {"power": power, "flow": flow})
    return None


def external_water(bundle: Any, windows: Any) -> WaterEvidence | None:
    flow, soil = val(bundle, "PUMP_01", "flow_rate"), delta(windows, "SOIL_01", "soil_moisture")
    if flow is not None and soil is not None and flow <= EPSILON and soil > EPSILON:
        return WaterEvidence("external_water", {"flow": flow, "soil_delta": soil})
    return None


def ratio_drift(bundle: Any, windows: Any, baseline: RatioBaseline) -> WaterEvidence | None:
    flow = val(bundle, "PUMP_01", "flow_rate")
    tank = delta(windows, "TANK_01", "level")
    soil = delta(windows, "SOIL_01", "soil_moisture")
    if (
        not baseline.warmup_complete
        or flow is None
        or flow <= FLOW_MIN
        or tank is None
        or soil is None
        or soil <= EPSILON
    ):
        return None
    ratio = abs(tank) / soil
    if abs(ratio - baseline.mean) > 2 * baseline.stddev:
        return WaterEvidence(
            "ratio_drift", {"ratio": ratio, "baseline": baseline.mean, "stddev": baseline.stddev}
        )
    return None


def fit_ph_baseline(samples: list[float]) -> float | None:
    """Learn the observed pH baseline; no agronomic threshold is introduced."""
    finite: list[float] = []
    for sample in samples:
        try:
            numeric = float(sample)
        except (TypeError, ValueError):
            continue
        if numeric == numeric and 0 <= numeric <= 14:
            finite.append(numeric)
    return mean(finite) if finite else None


def ph_advisory(
    bundle: Any, baseline_ph: float | None, tolerance: float = 2.0
) -> WaterEvidence | None:
    """Flag material pH movement for tank quality without gating irrigation."""
    ph = val(bundle, "PH_01", "ph")
    if ph is not None and baseline_ph is not None and abs(ph - baseline_ph) > tolerance:
        return WaterEvidence(
            "ph_baseline_deviation",
            {"ph": ph, "baseline_ph": baseline_ph},
            advisory=True,
        )
    return None


def diagnose(
    bundle: Any,
    windows: Any,
    baseline: RatioBaseline | None = None,
    baseline_ph: float | None = None,
) -> list[WaterEvidence]:
    evidence = [
        fn(bundle, windows)
        for fn in (pipe_leak, flow_tank_mismatch, dry_run_or_clogged_filter, external_water)
    ]
    if baseline is not None:
        evidence.append(ratio_drift(bundle, windows, baseline))
    evidence.append(ph_advisory(bundle, baseline_ph))
    return [item for item in evidence if item is not None]
