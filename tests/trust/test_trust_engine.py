from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contracts import ExpectedOutcome, Reading
from trust.expected import evaluate
from trust.freshness import freshness
from trust.physics import (
    diagnose,
    dry_run_or_clogged_filter,
    external_water,
    fit_ph_baseline,
    fit_ratio_baseline,
    flow_tank_mismatch,
    ph_advisory,
    pipe_leak,
    ratio_drift,
)
from trust.rules.registry import hard_fails, soft_rules
from trust.score import score_scope
from trust.snapshots import snapshot_record
from trust.states import ReadingState, assign_state
from trust.tier import Tier, TierState, evaluate_tier

pytestmark = pytest.mark.trust


def test_freshness_and_states_are_safe_and_exact() -> None:
    assert freshness(1, 1) == 1.0
    assert freshness(2, 1) == 0.5
    assert freshness(3, 1) == 0.0
    assert freshness(None, None) == 0.0
    assert assign_state({"status": "ok"}, age=1, ttl=1) is ReadingState.FRESH
    assert assign_state({"status": "ok"}, age=2, ttl=1) is ReadingState.STALE
    assert assign_state({"status": "warn"}) is ReadingState.SUSPECT
    assert assign_state({"status": "ok"}, present=False, absent_batches=3) is ReadingState.OFFLINE
    assert assign_state(None) is ReadingState.MISSING


def test_rule_registry_and_missing_data_contract() -> None:
    assert set(hard_fails()) == {"out_of_range", "source_not_ok", "stuck_at"}
    assert set(soft_rules()) == {
        "flow_without_tank_drop",
        "power_without_flow",
        "pump_on_soil_flat",
        "soil_rise_pump_off",
        "tank_drain_no_pump",
    }
    for predicate in [*hard_fails().values(), *soft_rules().values()]:
        assert predicate({}, {}) is False


def test_hard_and_soft_rule_conditions() -> None:
    assert hard_fails()["source_not_ok"]({"PH_01.ph": {"status": "warn"}}, {})
    assert hard_fails()["out_of_range"]({"PH_01.ph": 15}, {})
    assert soft_rules()["pump_on_soil_flat"](
        {"PUMP_01.flow_rate": 13.9}, {"SOIL_01.soil_moisture": [36, 36]}
    )
    assert soft_rules()["tank_drain_no_pump"]({"PUMP_01.flow_rate": 0}, {"TANK_01.level": [60, 59]})
    assert soft_rules()["flow_without_tank_drop"](
        {"PUMP_01.flow_rate": 13.9}, {"TANK_01.level": [60, 60]}
    )
    assert soft_rules()["power_without_flow"]({"PUMP_01.flow_rate": 0, "PUMP_01.power": 646}, {})
    assert soft_rules()["soil_rise_pump_off"](
        {"PUMP_01.flow_rate": 0}, {"SOIL_01.soil_moisture": [36, 37]}
    )


def test_stuck_sensor_needs_bit_identity_and_correlated_movement() -> None:
    windows = {
        "SOIL_01.soil_moisture": [36.0] * 12,
        "TANK_01.level": [60.0, 59.0],
        "PUMP_01.flow_rate": [13.9, 14.1],
    }
    assert hard_fails()["stuck_at"]({}, windows)
    assert not hard_fails()["stuck_at"]({}, {"SOIL_01.soil_moisture": [36.0] * 12})
    windows["SOIL_01.soil_moisture"] = [0.0] * 11 + [-0.0]
    assert not hard_fails()["stuck_at"]({}, windows)


def test_stale_freshness_flows_into_dcs_and_blocks_required_action() -> None:
    specs = {"irrigation_plan": {"SOIL_01.soil_moisture": {"weight": 1, "required": True}}}
    bundle = {"SOIL_01.soil_moisture": {"value": 36, "state": "STALE"}}
    snapshot = score_scope(
        bundle,
        {},
        "irrigation_plan",
        specs,
        ages={"SOIL_01.soil_moisture": 2},
        ttls={"SOIL_01.soil_moisture": 1},
    )
    assert snapshot.freshness == 0.5
    assert snapshot.completeness == 1.0
    assert snapshot.dcs == pytest.approx(0.775)
    assert snapshot.cap_applied is None
    assert snapshot.blocked_required_metrics == ("SOIL_01.soil_moisture",)
    assert snapshot.payload()["actionAllowed"] is False


def test_required_hard_fail_is_attributed_and_capped() -> None:
    specs = {
        "irrigation_plan": {
            "SOIL_01.soil_moisture": {"weight": 1, "required": True},
            "PUMP_01.flow_rate": {"weight": 9, "required": False},
        }
    }
    bundle = {
        "SOIL_01.soil_moisture": {"value": 120, "state": "FRESH"},
        "PUMP_01.flow_rate": {"value": 13.9, "state": "FRESH"},
    }
    snapshot = score_scope(bundle, {}, "irrigation_plan", specs)
    assert snapshot.dcs == 0.40
    assert snapshot.cap_applied == 0.40
    assert snapshot.rules_fired == ("out_of_range",)
    assert {
        "F",
        "C",
        "K",
        "dcsPolicyVersion",
        "cap_applied",
        "rules_fired",
    } <= snapshot.payload().keys()


def test_contract_reading_objects_are_consumed_without_losing_status() -> None:
    reading = Reading(
        "r_1",
        "SOIL_01",
        "soil_moisture",
        36.0,
        "%",
        "2026-08-16T00:00:00Z",
        "2026-08-16T00:00:00Z",
        1,
        "warn",
    )
    specs = {"irrigation_plan": {"SOIL_01.soil_moisture": {"weight": 1, "required": True}}}
    snapshot = score_scope({"SOIL_01.soil_moisture": reading}, {}, "irrigation_plan", specs)
    assert snapshot.rules_fired == ("source_not_ok",)
    assert snapshot.blocked_required_metrics == ("SOIL_01.soil_moisture",)


def test_consistency_penalties_apply_the_055_cap() -> None:
    specs = {
        "session_check": {
            "PUMP_01.flow_rate": {"weight": 1},
            "PUMP_01.power": {"weight": 1},
            "TANK_01.level": {"weight": 1},
        }
    }
    bundle = {
        "PUMP_01.flow_rate": {"value": 0, "state": "FRESH"},
        "PUMP_01.power": {"value": 646, "state": "FRESH"},
        "TANK_01.level": {"value": 59, "state": "FRESH"},
    }
    snapshot = score_scope(
        bundle,
        {"TANK_01.level": [60, 59]},
        "session_check",
        specs,
    )
    assert snapshot.consistency == pytest.approx(0.40)
    assert snapshot.dcs == 0.55
    assert snapshot.cap_applied == 0.55
    assert snapshot.rules_fired == ("power_without_flow", "tank_drain_no_pump")


def test_scopes_are_scored_independently() -> None:
    specs = {
        "irrigation_plan": {
            ("SOIL_01", "soil_moisture"): {"weight": 1, "required": "irrigation_plan"}
        },
        "tank_quality": {("TANK_01", "level"): {"weight": 1, "required": "tank_quality"}},
    }
    bundle = {
        "SOIL_01.soil_moisture": {"value": 120, "state": "FRESH"},
        "TANK_01.level": {"value": 60, "state": "FRESH"},
    }
    irrigation = score_scope(bundle, {}, "irrigation_plan", specs)
    tank = score_scope(bundle, {}, "tank_quality", specs)
    assert irrigation.blocked_required_metrics == ("SOIL_01.soil_moisture",)
    assert tank.blocked_required_metrics == ()
    assert tank.dcs == 1.0


def test_tier_drops_immediately_but_raise_requires_streak_and_dwell() -> None:
    now = datetime.now(UTC)
    auto = TierState(Tier.AUTO, now, 0)
    assert evaluate_tier(0.79, auto, now).tier is Tier.PROPOSE
    proposed = TierState(Tier.PROPOSE, now, 0)
    first_raise = evaluate_tier(0.86, proposed, now + timedelta(seconds=61))
    assert first_raise.tier is Tier.PROPOSE
    assert evaluate_tier(0.84, first_raise, now + timedelta(seconds=62)).raise_streak == 0
    assert evaluate_tier(0.86, first_raise, now + timedelta(seconds=62)).tier is Tier.AUTO


def test_tier_state_round_trips_for_persistence() -> None:
    now = datetime.now(UTC)
    state = TierState(Tier.PROPOSE, now, 1)
    assert TierState.from_payload(state.payload()) == state


def test_all_five_water_balance_diagnoses() -> None:
    pump_on = {"PUMP_01.flow_rate": 13.9, "PUMP_01.power": 646}
    assert pipe_leak(pump_on, {"TANK_01.level": [60, 59], "SOIL_01.soil_moisture": [36, 36]})
    assert flow_tank_mismatch(
        pump_on, {"TANK_01.level": [60, 60], "SOIL_01.soil_moisture": [36, 37]}
    )
    assert dry_run_or_clogged_filter({"PUMP_01.flow_rate": 0, "PUMP_01.power": 646}, {})
    assert external_water({"PUMP_01.flow_rate": 0}, {"SOIL_01.soil_moisture": [36, 38]})
    baseline = fit_ratio_baseline([(1, 1), (1, 1)])
    drift = ratio_drift(
        pump_on,
        {"TANK_01.level": [60, 58], "SOIL_01.soil_moisture": [36, 37]},
        baseline,
    )
    assert drift is not None and drift.diagnosis == "ratio_drift"
    assert fit_ratio_baseline([(1, 1)], elapsed_seconds=600).warmup_complete


def test_ph_is_learned_advisory_only() -> None:
    baseline_ph = fit_ph_baseline([9.9, 10.0, 10.1])
    assert baseline_ph == pytest.approx(10.0)
    assert ph_advisory({"PH_01.ph": 10}, baseline_ph) is None
    advisory = ph_advisory({"PH_01.ph": 4}, baseline_ph)
    assert advisory is not None and advisory.advisory
    evidence = diagnose({"PH_01.ph": 4}, {}, baseline_ph=baseline_ph)
    assert evidence == [advisory]


def test_expected_flow_trajectory_carries_both_assumption_names() -> None:
    outcome = ExpectedOutcome("PUMP_01.flow_rate", "at_least", 8.0, 0.0, "60s", "mqtt", "A1")
    result = evaluate(outcome, {"PUMP_01.flow_rate": [13.9, 4.5, 13.9]})
    assert result.result == "FAIL"
    assert result.observed == 4.5
    assert result.trajectory == (13.9, 4.5, 13.9)
    assert result.assumptionId == result.affectedAssumptionId == "A1"


def test_expected_outcome_is_inconclusive_without_evidence() -> None:
    outcome = ExpectedOutcome("SOIL_01.soil_moisture", "increase", 1.0, 0.0, "60s", "mqtt", "A3")
    result = evaluate(outcome, {})
    assert result.result == "INCONCLUSIVE"
    assert result.assumptionId == "A3"


def test_snapshot_record_matches_frozen_database_schema() -> None:
    specs = {"irrigation_plan": {"TANK_01.level": {"weight": 1, "required": True}}}
    snapshot = score_scope(
        {"TANK_01.level": {"value": 59.8, "state": "FRESH"}},
        {},
        "irrigation_plan",
        specs,
    )
    record = snapshot_record(snapshot, Tier.AUTO, 42, "ts_test")
    assert record == {
        "snapshot_id": "ts_test",
        "scope": "irrigation_plan",
        "dcs": 1.0,
        "f": 1.0,
        "c": 1.0,
        "k": 1.0,
        "cap_applied": None,
        "tier": "AUTO",
        "rules_fired": [],
        "dcs_policy_version": 1,
        "farm_state_version": 42,
    }


def test_score_scope_binds_source_state_version_and_evaluation_id():
    snapshot = score_scope(
        {"TANK_01.level": {"value": 59.8, "state": "FRESH"}},
        {},
        "irrigation_plan",
        source_state_version=42,
        evaluation_id="ev_1",
        evaluation_time="2026-08-16T00:00:00Z",
    )
    assert snapshot.source_state_version == 42
    assert snapshot.evaluation_id == "ev_1"
    assert snapshot.evaluation_time == "2026-08-16T00:00:00Z"


def test_score_scope_defaults_state_version_to_none_for_existing_callers():
    snapshot = score_scope({}, {}, "irrigation_plan")
    assert snapshot.source_state_version is None


def test_divergence_binds_source_state_version():
    outcome = ExpectedOutcome("TANK_01.level", "at_least", 50, 1, "5m", "TANK_01.level", "a1")
    readings = {"TANK_01": {"level": [60.0]}}
    divergence = evaluate(outcome, readings, source_state_version=42)
    assert divergence.source_state_version == 42
