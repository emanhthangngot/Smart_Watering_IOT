from datetime import UTC, datetime, timedelta

import pytest

from api.bootstrap import _extract_fresh_tank_level, authorize_schedule, build_schedule_runner
from api.service import FarmOpsService
from config import Config
from schedule.models import Schedule, ScheduleStatus

pytestmark = pytest.mark.tools


def _schedule(**overrides) -> Schedule:
    now = datetime.now(UTC)
    defaults = dict(
        schedule_id="sched-1",
        plan_revision_id="PLAN-1-V1",
        pump_id="PUMP_01",
        start_at=now,
        end_at=now + timedelta(minutes=10),
        status=ScheduleStatus.PENDING,
    )
    defaults.update(overrides)
    return Schedule(**defaults)


def _service_with_plan(*, status: str = "APPROVED") -> FarmOpsService:
    service = FarmOpsService()
    service.plans["PLAN-1-V1"] = {"status": status, "revisionHash": "hash-v1"}
    return service


def test_authorize_schedule_rejects_unknown_plan() -> None:
    service = FarmOpsService()
    assert authorize_schedule(service, _schedule()) is False


def test_authorize_schedule_rejects_missing_approval() -> None:
    service = _service_with_plan()
    assert authorize_schedule(service, _schedule()) is False


def test_authorize_schedule_rejects_wrong_revision_hash() -> None:
    service = _service_with_plan()
    now = datetime.now(UTC)
    service.approvals["approval-1"] = {
        "planRevisionId": "PLAN-1-V1",
        "decision": "APPROVE",
        "revisionHash": "stale-hash",
        "expiresAt": (now + timedelta(minutes=30)).isoformat(),
    }
    assert authorize_schedule(service, _schedule()) is False


def test_authorize_schedule_rejects_expired_approval() -> None:
    service = _service_with_plan()
    now = datetime.now(UTC)
    service.approvals["approval-1"] = {
        "planRevisionId": "PLAN-1-V1",
        "decision": "APPROVE",
        "revisionHash": "hash-v1",
        "expiresAt": (now - timedelta(minutes=1)).isoformat(),
    }
    assert authorize_schedule(service, _schedule()) is False


def test_authorize_schedule_accepts_matching_unexpired_approval() -> None:
    service = _service_with_plan()
    now = datetime.now(UTC)
    service.approvals["approval-1"] = {
        "planRevisionId": "PLAN-1-V1",
        "decision": "APPROVE",
        "revisionHash": "hash-v1",
        "expiresAt": (now + timedelta(minutes=30)).isoformat(),
    }
    assert authorize_schedule(service, _schedule()) is True


def test_extract_fresh_tank_level_ignores_stale_and_missing() -> None:
    snapshot = {
        "devices": [
            {"deviceCode": "TANK_01", "metrics": {"level": {"state": "STALE", "value": 40.0}}},
        ]
    }
    assert _extract_fresh_tank_level(snapshot) is None


def test_extract_fresh_tank_level_reads_fresh_value() -> None:
    snapshot = {
        "devices": [
            {"deviceCode": "TANK_01", "metrics": {"level": {"state": "FRESH", "value": 59.8}}},
        ]
    }
    assert _extract_fresh_tank_level(snapshot) == 59.8


def test_build_schedule_runner_returns_none_without_postgres(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_POSTGRES_DSN", "postgresql://nope:nope@127.0.0.1:1/nope")
    config = Config.from_env()
    service = FarmOpsService()
    assert build_schedule_runner(config, service) is None
