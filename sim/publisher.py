"""Publishes simulator batches in the same JSON shape as the real broker.

Design reference: plans/reports/plan.md §9.2,
plans/260816-0957-data-plane/phase-05-simulator.md. Same batch/publish
shape as plans/input_format.txt so ingest/normalize.py cannot tell a sim
batch from a real one. The runner (M4) sends pump commands into the sim in
`sim` mode; sim state updates feed back into the next published batch —
the actual closed loop for ACTUATION_TARGET=sim.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from config import Config
from ingest.clock import epoch_to_iso
from sim.faults import FaultFlags
from sim.world import WorldState

DEVICE_ORDER = ("PH_01", "PUMP_01", "SOIL_01", "SUN_01", "TANK_01", "WEATHER_01")

BatchSink = Callable[[dict], None]


def build_batch(
    world: WorldState,
    faults: FaultFlags,
    config: Config,
    epoch: int,
    scenario: str = "NORMAL",
) -> dict:
    metrics_by_device = world.metrics_by_device()
    devices = []
    for device_code in DEVICE_ORDER:
        if device_code in faults.offline_devices:
            continue
        devices.append(
            {
                "deviceCode": device_code,
                "status": "ok",
                "metrics": metrics_by_device[device_code],
            }
        )
    return {
        "timestamp": epoch_to_iso(epoch),
        "epoch": epoch,
        "environment": config.environment,
        "scenario": scenario,
        "devices": devices,
        "teamCode": config.team_code,
    }


class SimPublisher:
    """Ticks the shared WorldState and emits one batch per cadence period.

    `pump_command` is a callable so the schedule runner (M4, sim mode) can
    push the current desired pump state without this module depending on
    the runner's internals.
    """

    def __init__(
        self,
        world: WorldState,
        faults: FaultFlags,
        config: Config,
        sink: BatchSink,
        cadence_s: float = 10.0,
        pump_command: Callable[[], bool] | None = None,
    ) -> None:
        self._world = world
        self._faults = faults
        self._config = config
        self._sink = sink
        self._cadence_s = cadence_s
        self._pump_command = pump_command or (lambda: False)

    def tick(self, epoch: int | None = None) -> dict:
        epoch = epoch if epoch is not None else int(time.time())
        self._world.tick(
            self._cadence_s,
            self._pump_command(),
            pump_no_effect=self._faults.pump_no_effect,
            tank_leak=self._faults.tank_leak,
        )
        batch = build_batch(self._world, self._faults, self._config, epoch)
        self._sink(batch)
        return batch

    def run_forever(self) -> None:
        while True:
            self.tick()
            time.sleep(self._cadence_s)
