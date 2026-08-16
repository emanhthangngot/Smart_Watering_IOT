"""Process-startup wiring: builds the real sim/ingest/trust/agents pipeline
and plugs it into `api.service.service` and `api.runtime.runtime`.

Called once from `api.main`'s lifespan, before `runtime.start()`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from config import Config
from trust.score import ScoreSnapshot
from trust.tier import Tier

from .pipeline import FarmPipeline
from .runtime import runtime
from .service import service
from .workflow import SimFarmWorkflow

logger = logging.getLogger(__name__)

INGEST_INTERVAL_S = 5.0

_pipeline: FarmPipeline | None = None
_workflow: SimFarmWorkflow | None = None
_ingest_task: asyncio.Task[None] | None = None


class _SimAdminAdapter:
    """Backs `POST /sim/*` fault-injection controls with the same live
    world/faults the ingest loop reads every tick — an operator-triggered
    `sensor_stuck` really freezes the next published batch, per
    `sim/faults.py`."""

    def __init__(self, pipeline: FarmPipeline) -> None:
        self._pipeline = pipeline

    def command(self, operation: str, params: Mapping[str, object]) -> Mapping[str, Any]:
        faults, world = self._pipeline.faults, self._pipeline.world
        if operation == "reset":
            faults.pump_no_effect = False
            faults.tank_leak = False
            for device, metric in list(faults.stuck_metrics):
                faults.clear_sensor_stuck(world, device, metric)
            for device in list(faults.offline_devices):
                faults.clear_device_offline(device)
            return {"reset": True}
        fault = str(params.get("fault"))
        if operation == "inject-fault":
            if fault == "pump_no_effect":
                faults.pump_no_effect = True
            elif fault == "tank_leak":
                faults.tank_leak = True
            elif fault == "sensor_stuck":
                faults.set_sensor_stuck(world, "SOIL_01", "soil_moisture")
            elif fault == "device_offline":
                faults.set_device_offline("PUMP_01")
            else:
                raise ValueError(f"unsupported fault: {fault!r}")
            return {"injected": fault}
        if operation == "clear-fault":
            if fault == "pump_no_effect":
                faults.pump_no_effect = False
            elif fault == "tank_leak":
                faults.tank_leak = False
            elif fault == "sensor_stuck":
                faults.clear_sensor_stuck(world, "SOIL_01", "soil_moisture")
            elif fault == "device_offline":
                faults.clear_device_offline("PUMP_01")
            else:
                raise ValueError(f"unsupported fault: {fault!r}")
            return {"cleared": fault}
        raise ValueError(f"unsupported simulator operation: {operation!r}")


def _open_task_exists(device: str) -> bool:
    return any(
        task.get("deviceCode") == device and task.get("status") != "resolved"
        for task in service.tasks.values()
    )


def _on_trust_finding(
    device: str, snapshot: ScoreSnapshot, tier: Tier | None, rules: tuple[str, ...]
) -> None:
    """Raises a real inspection task from a device trust rule firing —
    acceptance criterion 6 (`api.pipeline.FarmPipeline._raise_findings`)."""
    if _open_task_exists(device):
        return
    priority = "CRITICAL" if tier is Tier.INVESTIGATE else "HIGH"
    service.add_task(
        {
            "id": f"task_{uuid.uuid4().hex[:10]}",
            "title": f"Inspect {device}",
            "deviceCode": device,
            "reason": f"Trust rule(s) fired: {', '.join(rules)} (DCS={snapshot.dcs:.2f})",
            "instructions": (
                "Verify device wiring/power and confirm this sensor's reading against a "
                "manual check before trusting it again."
            ),
            "priority": priority,
            "status": "unread",
            "evidenceRefs": [],
            "createdAt": datetime.now(UTC).isoformat(),
        }
    )


async def _ingest_loop(pipeline: FarmPipeline) -> None:
    while True:
        try:
            await pipeline.tick()
        except Exception:
            logger.exception("pipeline tick failed")
        await asyncio.sleep(pipeline.cadence_s)


def build() -> tuple[FarmPipeline, SimFarmWorkflow]:
    """Construct the pipeline/workflow and wire them into the service +
    runtime coordinator. Idempotent — safe to call more than once."""
    global _pipeline, _workflow
    if _pipeline is not None and _workflow is not None:
        return _pipeline, _workflow

    config = Config.from_env()
    pipeline = FarmPipeline(config, cadence_s=INGEST_INTERVAL_S)
    pipeline.on_trust_finding = _on_trust_finding

    workflow = SimFarmWorkflow(pipeline, service)
    service.configure_workflow(workflow)
    service.configure_telemetry(pipeline)
    service.configure_simulator(_SimAdminAdapter(pipeline), workflow.idempotency)

    # Only the schedule runner is real M4-grade wiring here. Startup recovery
    # (api/recovery.py) and retention (api/retention.py) both need durable
    # storage for approvals/actions/schedules and the sensor-reading tables
    # respectively; this pipeline keeps plans/approvals/schedules in-memory
    # (service.py's existing façade) and has not built that persistence, so
    # wiring a no-op there would misreport "READY" for an integration that
    # is not actually recovery-safe. Left unconfigured — reported as scope
    # narrowed, not faked.
    runtime.configure(
        startup_recovery=None,  # type: ignore[arg-type]  # honest BLOCKED_M1, see note above
        schedule_runner=workflow.schedule_runner,
        retention_job=None,  # type: ignore[arg-type]  # honest BLOCKED_M1, see note above
    )

    _pipeline, _workflow = pipeline, workflow
    return pipeline, workflow


async def start() -> None:
    global _ingest_task
    pipeline, workflow = build()
    workflow.bind_loop(asyncio.get_running_loop())
    if _ingest_task is None:
        _ingest_task = asyncio.create_task(_ingest_loop(pipeline), name="farmops-sim-ingest")


async def stop() -> None:
    global _ingest_task
    if _ingest_task is not None:
        _ingest_task.cancel()
        try:
            await _ingest_task
        except asyncio.CancelledError:
            pass
        _ingest_task = None


__all__ = ["build", "start", "stop"]
