from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.service import service
from tools.idempotency import InMemoryIdempotencyStore

pytestmark = pytest.mark.tools


@pytest.fixture(autouse=True)
def reset_service(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("OPERATOR_ACTOR", "operator-kiet")
    monkeypatch.setenv("ACTUATION_TARGET", "none")
    service.requests.clear()
    service.plans.clear()
    service.approvals.clear()
    service.tasks.clear()
    service.timeline.clear()
    service.explanations.clear()
    service.audit.clear()
    service.simulator_control = None
    service.workflow = None


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/farm/request", {"intent": "IRRIGATION", "scope": "KHU_A", "text": "Tưới"}),
        ("/approvals/PLAN-1-V1/approve", {"revisionHash": "hash-v1"}),
        ("/approvals/PLAN-1-V1/reject", {"revisionHash": "hash-v1"}),
        ("/tasks/task-1/acknowledge", None),
        ("/tasks/task-1/resolve", None),
        ("/sim/inject-fault", {"commandId": "cmd-1", "params": {}}),
    ],
)
def test_all_writes_require_operator_token(path, body) -> None:
    client = TestClient(app)
    assert client.post(path, json=body).status_code == 401


def test_farm_request_actor_is_derived() -> None:
    client = TestClient(app)
    body = {"intent": "IRRIGATION", "scope": "KHU_A", "text": "Tưới Khu A", "actor": "forged"}
    response = client.post(
        "/farm/request",
        json=body,
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 200
    assert service.audit[-1]["actor"] == "operator-kiet"
    assert service.audit[-1]["tokenId"] != "test-operator-token"
    assert service.requests[response.json()["traceId"]]["status"] == "BLOCKED_DEPENDENCY"


def test_farm_request_is_submitted_to_configured_workflow() -> None:
    class Workflow:
        def __init__(self):
            self.requests = []

        def submit_request(self, request):
            self.requests.append(request)

    workflow = Workflow()
    service.configure_workflow(workflow)
    response = TestClient(app).post(
        "/farm/request",
        json={"intent": "IRRIGATION", "scope": "KHU_A", "text": "Tưới Khu A"},
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 200
    trace_id = response.json()["traceId"]
    assert service.requests[trace_id]["status"] == "ACCEPTED"
    assert workflow.requests[0]["traceId"] == trace_id


def test_approval_requires_current_revision_hash() -> None:
    client = TestClient(app)
    service.plans["PLAN-1-V1"] = {
        "planRevisionId": "PLAN-1-V1",
        "revisionHash": "hash-v1",
        "status": "PROPOSED",
    }
    headers = {"X-Operator-Token": "test-operator-token"}
    mismatch = client.post(
        "/approvals/PLAN-1-V1/approve",
        json={"revisionHash": "old-hash", "actor": "forged"},
        headers=headers,
    )
    assert mismatch.status_code == 409
    accepted = client.post(
        "/approvals/PLAN-1-V1/approve",
        json={"revisionHash": "hash-v1", "actor": "forged"},
        headers=headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["approver"] == "operator-kiet"
    assert service.plans["PLAN-1-V1"]["status"] == "APPROVED"
    duplicate = client.post(
        "/approvals/PLAN-1-V1/approve",
        json={"revisionHash": "hash-v1"},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_open_blocking_challenge_prevents_approval() -> None:
    client = TestClient(app)
    service.plans["PLAN-1-V1"] = {
        "planRevisionId": "PLAN-1-V1",
        "revisionHash": "hash-v1",
        "status": "PROPOSED",
        "challenges": [{"blocking": True, "status": "OPEN"}],
    }
    response = client.post(
        "/approvals/PLAN-1-V1/approve",
        json={"revisionHash": "hash-v1"},
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 409


def test_task_lifecycle_is_unread_acknowledged_resolved() -> None:
    client = TestClient(app)
    service.tasks["task-1"] = {"taskId": "task-1", "status": "UNREAD"}
    headers = {"X-Operator-Token": "test-operator-token"}
    invalid = client.post("/tasks/task-1/resolve", headers=headers)
    assert invalid.status_code == 409
    assert client.post("/tasks/task-1/acknowledge", headers=headers).status_code == 200
    assert client.post("/tasks/task-1/resolve", headers=headers).status_code == 200


def test_sim_write_is_hidden_when_target_is_none() -> None:
    client = TestClient(app)
    response = client.post(
        "/sim/pump-start",
        json={"commandId": "cmd-1", "params": {"pump": "PUMP_01"}},
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 404


def test_sim_mode_fails_honestly_without_adapter_and_audits_real_adapter() -> None:
    class FakeSimulator:
        def __init__(self):
            self.calls = []

        def command(self, operation, params):
            self.calls.append((operation, dict(params)))
            return {"status": "ACCEPTED", "operation": operation, "params": params}

    client = TestClient(app)
    headers = {"X-Operator-Token": "test-operator-token"}
    service.simulator_control = None
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ACTUATION_TARGET", "sim")
        unavailable = client.post(
            "/sim/inject-fault",
            json={"commandId": "cmd-1", "params": {}},
            headers=headers,
        )
        assert unavailable.status_code == 503
        simulator = FakeSimulator()
        service.configure_simulator(simulator, InMemoryIdempotencyStore())
        accepted = client.post(
            "/sim/inject-fault",
            json={"commandId": "cmd-2", "params": {"fault": "pump_no_effect"}},
            headers=headers,
        )
        replay = client.post(
            "/sim/inject-fault",
            json={"commandId": "cmd-2", "params": {"fault": "pump_no_effect"}},
            headers=headers,
        )
        collision = client.post(
            "/sim/clear-fault",
            json={"commandId": "cmd-2", "params": {"fault": "pump_no_effect"}},
            headers=headers,
        )
        forbidden = client.post(
            "/sim/pump-start",
            json={"commandId": "cmd-3", "params": {"pump": "PUMP_01"}},
            headers=headers,
        )
        invalid_fault = client.post(
            "/sim/inject-fault",
            json={"commandId": "cmd-4", "params": {"fault": "arbitrary_code"}},
            headers=headers,
        )
    assert accepted.status_code == 200
    assert replay.json()["deliveryStatus"] == "DUPLICATE_REPLAY"
    assert collision.status_code == 400
    assert forbidden.status_code == 400
    assert invalid_fault.status_code == 400
    assert len(simulator.calls) == 1
    assert service.audit[-1]["event"] == "sim.command.requested"
    assert any(row["event"] == "sim.command.completed" for row in service.audit)
    assert service.audit[-1]["actor"] == "operator-kiet"


def test_blank_configured_actor_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_ACTOR", "   ")
    response = TestClient(app).post(
        "/farm/request",
        json={"intent": "IRRIGATION", "scope": "KHU_A", "text": "Tưới"},
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 401


def test_uncertain_simulator_command_is_not_blindly_retried(monkeypatch) -> None:
    class CommitThenFailSimulator:
        def __init__(self):
            self.calls = 0

        def command(self, operation, params):
            del operation, params
            self.calls += 1
            raise TimeoutError("response lost")

    monkeypatch.setenv("ACTUATION_TARGET", "sim")
    simulator = CommitThenFailSimulator()
    service.configure_simulator(simulator, InMemoryIdempotencyStore())
    client = TestClient(app)
    headers = {"X-Operator-Token": "test-operator-token"}
    body = {"commandId": "cmd-uncertain", "params": {"fault": "tank_leak"}}
    first = client.post("/sim/inject-fault", json=body, headers=headers)
    retry = client.post("/sim/inject-fault", json=body, headers=headers)
    assert first.status_code == 503
    assert retry.status_code == 409
    assert simulator.calls == 1


def test_expired_approval_and_stale_proposal_are_continuously_expired() -> None:
    now = datetime.now(UTC)
    service.plans["PLAN-1-V1"] = {
        "planRevisionId": "PLAN-1-V1",
        "revisionHash": "hash-v1",
        "status": "APPROVED",
    }
    service.approvals["approval-1"] = {
        "approvalId": "approval-1",
        "planRevisionId": "PLAN-1-V1",
        "revisionHash": "hash-v1",
        "expiresAt": (now - timedelta(seconds=1)).isoformat(),
    }
    service.plans["PLAN-2-V1"] = {
        "planRevisionId": "PLAN-2-V1",
        "revisionHash": "hash-v2",
        "status": "PROPOSED",
        "createdAt": (now - timedelta(minutes=31)).isoformat(),
    }
    assert service.expire_stale_plans(now) == 2
    assert service.plans["PLAN-1-V1"]["status"] == "EXPIRED"
    assert service.plans["PLAN-2-V1"]["status"] == "EXPIRED"


def test_read_endpoints_are_available_without_auth() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/farm/state").status_code == 200
    assert client.get("/trust/current").json()["status"] == "UNAVAILABLE"
