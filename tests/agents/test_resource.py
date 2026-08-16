from datetime import UTC, datetime, timedelta

import pytest

from agents.messages import ResourceInput
from agents.resource import evaluate_resource

pytestmark = pytest.mark.agents


def resource(**overrides) -> ResourceInput:
    values = {
        "level_pct": 60,
        "safe_reserve_pct": 20,
        "active_reserved_drawdown_pct": 10,
        "requested_drawdown_pct": 30,
        "farm_day": "2026-08-16",
        "timezone": "Asia/Ho_Chi_Minh",
        "ledger_as_of": datetime(2026, 8, 16),
        "now": datetime(2026, 8, 16, 0, 1),
        "source_state_version": 8,
    }
    values.update(overrides)
    return ResourceInput(**values)


def test_exact_budget_is_advisory_accept() -> None:
    result = evaluate_resource(resource())
    assert result.accepted and result.available_drawdown_pct == 40


def test_active_reservation_is_in_budget_arithmetic() -> None:
    result = evaluate_resource(resource(active_reserved_drawdown_pct=11))
    assert not result.accepted and "exceeds" in result.reason


def test_conflict_stale_and_missing_facts_request_or_reject() -> None:
    assert not evaluate_resource(resource(schedule_conflicts=("pump-window",))).accepted
    assert evaluate_resource(
        resource(now=datetime(2026, 8, 16) + timedelta(minutes=6))
    ).needs_more_evidence
    assert evaluate_resource(resource(level_pct=None)).needs_more_evidence
    assert evaluate_resource(resource(now=None)).needs_more_evidence


def test_naive_and_aware_datetimes_request_more_evidence() -> None:
    result = evaluate_resource(resource(now=datetime(2026, 8, 16, 0, 1, tzinfo=UTC)))
    assert result.needs_more_evidence and not result.accepted
