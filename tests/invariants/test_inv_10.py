"""INV-10: every threshold constant must be satisfied by the NORMAL baseline
values observed in the real payload (plans/reports/plan.md §3.1) — a
threshold that blocks the operating path on day-one NORMAL data is a design
bug (§5.1's pH lesson: agronomy-textbook thresholds must not gate on data
whose own baseline sits outside them).

Owner: shared / append-only (tests/invariants/). M1 feat/data-plane authors
this file with the threshold constants it owns (TTL, cadence, watermark,
skew, presence) plus the hard-fail physical-range bounds from §4.3/§5.1,
which are fixed by the design doc regardless of which branch enforces them.
Later owners (e.g. M2 for trust/'s own thresholds) append their own checks
below the marker — never reorder existing checks.
"""

from __future__ import annotations

import pytest

from ingest.cadence import BOOTSTRAP_PERIOD_S, TTL_CEIL_S, TTL_FLOOR_S, freshness, ttl_seconds
from ingest.clock import SKEW_WARN_THRESHOLD_S, TIME_FIELD_MISMATCH_THRESHOLD_S, WATERMARK_LAG_S
from ingest.presence import DEFAULT_OFFLINE_BATCHES
from registry.specs import SPECS

pytestmark = pytest.mark.invariants

# plans/reports/plan.md §3.1 — NORMAL baseline values observed in the real
# FARM payload. Used as the ground truth every threshold below is checked
# against.
NORMAL_BASELINE = {
    ("PUMP_01", "flow_rate"): 13.9,
    ("PUMP_01", "power"): 646.3,
    ("SOIL_01", "soil_moisture"): 36.0,
    ("SOIL_01", "temperature"): 26.1,
    ("TANK_01", "level"): 59.8,
    ("SUN_01", "lux"): 49833.3,
    ("PH_01", "ph"): 10.0,
    ("WEATHER_01", "temperature"): 24.3,
    ("WEATHER_01", "humidity"): 66.9,
}

# §3.1: "Đặt flow_min = 0.6 × nền quan sát (≈ 8.3 L/min) ... hoặc chốt cứng
# 8 L/min." Chosen here as the hard floor so the invariant is deterministic.
FLOW_MIN_L_MIN = 8.0

# §4.3 hard-fail out_of_range physical bounds.
PH_RANGE = (0.0, 14.0)
PCT_RANGE = (0.0, 100.0)  # soil_moisture, tank level


def test_registry_ttl_batches_at_least_one():
    for spec in SPECS:
        assert spec.ttl_batches >= 1, f"{spec.key}: ttl_batches must be >=1"


def test_ttl_clamped_within_floor_and_ceiling():
    for spec in SPECS:
        ttl_s = ttl_seconds(spec.ttl_batches, BOOTSTRAP_PERIOD_S)
        assert TTL_FLOOR_S <= ttl_s <= TTL_CEIL_S


def test_baseline_reading_arriving_on_time_is_fully_fresh():
    """A reading that arrives exactly on the bootstrap cadence (age == one
    batch period) must never already be discounted — else the very first
    batch after startup would suspend plans on healthy data."""
    for spec in SPECS:
        ttl_s = ttl_seconds(spec.ttl_batches, BOOTSTRAP_PERIOD_S)
        assert freshness(BOOTSTRAP_PERIOD_S, ttl_s) == 1.0


def test_flow_min_does_not_block_normal_pump_operation():
    baseline_flow = NORMAL_BASELINE[("PUMP_01", "flow_rate")]
    assert baseline_flow > FLOW_MIN_L_MIN, (
        f"flow_min={FLOW_MIN_L_MIN} would flag the NORMAL baseline flow "
        f"({baseline_flow}) as pump-not-running on batch 1 — this is exactly "
        "the A1 PUMP_FLOW_MIN self-invalidation failure mode §3.1 warns about."
    )


def test_ph_hard_fail_range_admits_normal_baseline():
    lo, hi = PH_RANGE
    baseline_ph = NORMAL_BASELINE[("PH_01", "ph")]
    assert lo <= baseline_ph <= hi, (
        "§5.1: pH out_of_range must only reject physically impossible values "
        "([0,14]) — an agronomy-textbook range would reject the NORMAL "
        f"baseline ph={baseline_ph} on the very first batch."
    )


def test_percent_hard_fail_range_admits_normal_baselines():
    lo, hi = PCT_RANGE
    for key in (("SOIL_01", "soil_moisture"), ("TANK_01", "level")):
        value = NORMAL_BASELINE[key]
        assert lo <= value <= hi


def test_offline_batches_threshold_is_positive():
    assert DEFAULT_OFFLINE_BATCHES >= 1


def test_watermark_and_skew_thresholds_are_positive():
    assert WATERMARK_LAG_S > 0
    assert SKEW_WARN_THRESHOLD_S > 0
    assert TIME_FIELD_MISMATCH_THRESHOLD_S > 0


# --- M2 feat/trust-engine: append trust/'s own threshold checks below,
# never reorder the checks above. ---
