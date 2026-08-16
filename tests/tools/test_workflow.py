import asyncio

import pytest

from api.service import FarmOpsService
from api.workflow import AgentWorkflow

pytestmark = pytest.mark.tools


class _FakeReadModel:
    def __init__(self, snapshot: dict, *, error: Exception | None = None) -> None:
        self._snapshot = snapshot
        self._error = error

    async def snapshot(self) -> dict:
        if self._error is not None:
            raise self._error
        return self._snapshot


def _fresh(value: float, reading_id: str = "r_aaaaaaaaaaaaaaaaaaaaaaaa") -> dict:
    return {"state": "FRESH", "value": value, "readingId": reading_id}


def _snapshot(
    *,
    state_version: int = 42,
    tank: dict | None = None,
    soil: dict | None = None,
) -> dict:
    return {
        "farmStateVersion": state_version,
        "devices": [
            {"deviceCode": "TANK_01", "metrics": {"level": tank or _fresh(59.8, "r_tank000000")}},
            {
                "deviceCode": "SOIL_01",
                "metrics": {"soil_moisture": soil or _fresh(36.0, "r_soil000000")},
            },
        ],
    }


def _request(trace_id: str = "trace_1", lineage_id: str = "PLAN-TEST01") -> dict:
    return {
        "traceId": trace_id,
        "planLineageId": lineage_id,
        "intent": "IRRIGATION",
        "scope": "A",
    }


async def _submit(workflow: AgentWorkflow, request: dict) -> None:
    # Mirrors FastAPI running the sync endpoint in a threadpool while the
    # event loop (needed by run_coroutine_threadsafe inside submit_request)
    # keeps running on the calling thread.
    await asyncio.to_thread(workflow.submit_request, request)


def _build(service: FarmOpsService, read_model, loop) -> AgentWorkflow:
    return AgentWorkflow(read_model, service, loop)


def test_blocked_when_no_telemetry_yet() -> None:
    async def scenario() -> None:
        service = FarmOpsService()
        workflow = _build(
            service, _FakeReadModel(_snapshot(state_version=0)), asyncio.get_running_loop()
        )
        request = _request()
        service.timeline[request["traceId"]] = []
        await _submit(workflow, request)
        events = service.timeline[request["traceId"]]
        assert events[-1]["type"] == "FARM_REQUEST_NOT_PLANNED"
        assert "telemetry" in events[-1]["reason"]
        assert not service.plans

    asyncio.run(scenario())


def test_blocked_when_tank_not_fresh() -> None:
    async def scenario() -> None:
        service = FarmOpsService()
        stale_tank = {"state": "STALE", "value": 59.8, "readingId": "r_tank000000"}
        workflow = _build(
            service, _FakeReadModel(_snapshot(tank=stale_tank)), asyncio.get_running_loop()
        )
        request = _request()
        service.timeline[request["traceId"]] = []
        await _submit(workflow, request)
        events = service.timeline[request["traceId"]]
        assert events[-1]["type"] == "FARM_REQUEST_NOT_PLANNED"
        assert not service.plans

    asyncio.run(scenario())


def test_proposes_a_plan_with_action_when_soil_is_dry_and_resource_accepts() -> None:
    async def scenario() -> None:
        service = FarmOpsService()
        soil = _fresh(20.0, "r_soil000000")  # below SOIL_MOISTURE_URGENCY_THRESHOLD (40)
        workflow = _build(service, _FakeReadModel(_snapshot(soil=soil)), asyncio.get_running_loop())
        request = _request()
        service.timeline[request["traceId"]] = []
        await _submit(workflow, request)

        assert "PLAN-TEST01-V1" in service.plans
        plan = service.plans["PLAN-TEST01-V1"]
        assert plan["status"] == "PROPOSED"
        assert plan["revisionHash"].startswith("rh_")
        assert len(plan["actions"]) == 1
        assert plan["actions"][0]["pumpId"] == "PUMP_01"
        assert plan["requiresApproval"] is True
        assert plan["evidenceRefs"] == ["r_tank000000#level", "r_soil000000#soil_moisture"]
        events = service.timeline[request["traceId"]]
        assert events[-1]["type"] == "PLAN_PROPOSED"

    asyncio.run(scenario())


def test_proposes_a_no_op_plan_when_soil_is_healthy() -> None:
    async def scenario() -> None:
        service = FarmOpsService()
        soil = _fresh(80.0, "r_soil000000")  # well above threshold — no irrigation needed
        workflow = _build(service, _FakeReadModel(_snapshot(soil=soil)), asyncio.get_running_loop())
        request = _request()
        service.timeline[request["traceId"]] = []
        await _submit(workflow, request)

        plan = service.plans["PLAN-TEST01-V1"]
        assert plan["actions"] == []
        assert plan["requiresApproval"] is False

    asyncio.run(scenario())


def test_reject_does_not_fall_through_to_planning() -> None:
    """Resource REJECT routes to "planner" with event=REVISE (agents/coordinator.py),
    not PROPOSE — this must not be mistaken for a green light to build a plan."""

    async def scenario() -> None:
        service = FarmOpsService()
        # Tank at 15% is below the 20% safe reserve -> available_drawdown_pct=0,
        # and the fixed 5% request exceeds it -> evaluate_resource REJECTs.
        tank = _fresh(15.0, "r_tank000000")
        workflow = _build(service, _FakeReadModel(_snapshot(tank=tank)), asyncio.get_running_loop())
        request = _request()
        service.timeline[request["traceId"]] = []
        await _submit(workflow, request)

        assert not service.plans
        events = service.timeline[request["traceId"]]
        assert events[-1]["type"] == "FARM_REQUEST_NOT_PLANNED"
        assert "resource" in events[-1]["reason"]

    asyncio.run(scenario())


def test_snapshot_failure_propagates_for_the_existing_503_path() -> None:
    async def scenario() -> None:
        service = FarmOpsService()
        workflow = _build(
            service,
            _FakeReadModel({}, error=ConnectionError("db unreachable")),
            asyncio.get_running_loop(),
        )
        with pytest.raises(ConnectionError):
            await _submit(workflow, _request())

    asyncio.run(scenario())
