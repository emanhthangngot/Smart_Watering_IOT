from datetime import UTC, datetime

import pytest

from verify.action import verify_action
from verify.ledger import (
    InMemoryWaterLedger,
    Reconciliation,
    WaterLedgerEntry,
    active_planned_drawdown,
    available_drawdown_budget,
    reconcile,
)
from verify.outcome import verify_outcome

pytestmark = pytest.mark.tools


def test_action_pass_does_not_force_outcome_pass() -> None:
    action = verify_action(
        expected_id="schedule-1",
        expected_status="PENDING",
        expected_params={"minutes": 10},
        post_result={"id": "schedule-1", "status": "PENDING", "params": {"minutes": 10}},
        read_back={"id": "schedule-1", "status": "PENDING", "params": {"minutes": 10}},
        window="immediate",
    )
    outcome = verify_outcome(
        actuation_target="sim",
        pump_activity_observed=True,
        evidence_usable=True,
        expected_met=False,
        expected={"flow_min": 8.0},
        observed={"flow_rate": 4.5},
        window="10m",
        evidence_refs=["r_flow#flow_rate"],
    )
    assert action.result == "PASS"
    assert outcome.result == "FAIL"


def test_observational_mode_without_pump_activity_is_inconclusive() -> None:
    outcome = verify_outcome(
        actuation_target="none",
        pump_activity_observed=False,
        evidence_usable=True,
        expected_met=True,
        expected={"soil_delta": ">0"},
        observed={"soil_delta": 0},
        window="10m",
    )
    assert outcome.result == "INCONCLUSIVE"


def test_ledger_reconciliation_and_daily_budget() -> None:
    assert (
        reconcile(
            observed_tank_drawdown_pct=None,
            observed_flow_integral=10,
            expected_drawdown_per_flow_unit=0.1,
            readings_usable=False,
        )
        is Reconciliation.INCONCLUSIVE
    )
    assert (
        reconcile(
            observed_tank_drawdown_pct=0.4,
            observed_flow_integral=10,
            expected_drawdown_per_flow_unit=0.1,
            readings_usable=True,
        )
        is Reconciliation.UNDER_DELIVERED
    )
    now = datetime.now(UTC)
    ledger = InMemoryWaterLedger()
    ledger.add(
        WaterLedgerEntry(
            entry_id="ledger-1",
            plan_revision_id="PLAN-1-V1",
            action_id="action-1",
            window_start=now,
            window_end=now,
            planned_drawdown_pct=6.5,
            planned_pump_minutes=18,
            observed_tank_drawdown_pct=None,
            observed_flow_integral=None,
            observed_pump_minutes=None,
            reconciliation=Reconciliation.INCONCLUSIVE,
            active=True,
        )
    )
    committed = active_planned_drawdown(ledger, now)
    assert committed == 6.5
    assert available_drawdown_budget(59.8, 20.0, committed) == pytest.approx(33.3)


def test_action_verification_rejects_mismatched_post_response() -> None:
    verification = verify_action(
        expected_id="schedule-1",
        expected_status="PENDING",
        expected_params={"minutes": 10},
        post_result={"id": "schedule-1", "status": "FAILED", "params": {"minutes": 999}},
        read_back={"id": "schedule-1", "status": "PENDING", "params": {"minutes": 10}},
        window="immediate",
    )
    assert verification.result == "FAIL"


def test_unknown_actuation_target_and_invalid_budget_fail_closed() -> None:
    with pytest.raises(ValueError):
        verify_outcome(
            actuation_target="real",
            pump_activity_observed=True,
            evidence_usable=True,
            expected_met=True,
            expected={},
            observed={},
            window="1m",
        )
    with pytest.raises(ValueError):
        available_drawdown_budget(60.0, 20.0, -10.0)
