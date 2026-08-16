import asyncio

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.runtime import RuntimeCoordinator, runtime

pytestmark = pytest.mark.tools


def test_runtime_runs_recovery_before_background_components_and_stops_cleanly() -> None:
    events = []

    class Runner:
        async def run_forever(self):
            events.append("runner")
            await asyncio.Event().wait()

    async def scenario() -> None:
        coordinator = RuntimeCoordinator(
            startup_recovery=lambda: events.append("recovery"),
            schedule_runner=Runner(),
            retention_job=lambda: events.append("retention"),
            expiry_job=lambda: events.append("expiry"),
            retention_interval_seconds=0.01,
            expiry_interval_seconds=0.01,
        )
        await coordinator.start()
        await asyncio.sleep(0.03)
        assert events[0:2] == ["recovery", "expiry"]
        assert "runner" in events
        assert "retention" in events
        assert coordinator.snapshot()["started"] is True
        await coordinator.stop()
        assert coordinator.snapshot()["started"] is False

    asyncio.run(scenario())


def test_fastapi_lifespan_starts_expiry_and_reports_missing_integrations(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", "token")
    with TestClient(app) as client:
        snapshot = client.get("/health").json()["runtime"]
        assert snapshot["started"] is True
        assert snapshot["expiry"] == "RUNNING"
        assert snapshot["recovery"] == "BLOCKED_M1"
    assert runtime.snapshot()["started"] is False


def test_recovery_failure_prevents_runtime_from_starting() -> None:
    async def scenario() -> None:
        coordinator = RuntimeCoordinator(
            startup_recovery=lambda: (_ for _ in ()).throw(RuntimeError("database unavailable"))
        )
        with pytest.raises(RuntimeError):
            await coordinator.start()
        assert coordinator.snapshot()["started"] is False

    asyncio.run(scenario())
