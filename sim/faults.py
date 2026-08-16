"""Fault flag application for the simulator.

Design reference: plans/reports/plan.md §9.2,
plans/260816-0957-data-plane/phase-05-simulator.md. Fault injection is a
test tool, not a demo button (§10.5) — flags are set programmatically by
test/replay code, not exposed as a user-facing control here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.world import WorldState


@dataclass
class FaultFlags:
    pump_no_effect: bool = False
    tank_leak: bool = False
    stuck_metrics: set[tuple[str, str]] = field(default_factory=set)
    offline_devices: set[str] = field(default_factory=set)

    def set_sensor_stuck(self, world: WorldState, device_code: str, metric: str) -> None:
        self.stuck_metrics.add((device_code, metric))
        world.freeze(device_code, metric)

    def clear_sensor_stuck(self, world: WorldState, device_code: str, metric: str) -> None:
        self.stuck_metrics.discard((device_code, metric))
        world.unfreeze(device_code, metric)

    def set_device_offline(self, device_code: str) -> None:
        self.offline_devices.add(device_code)

    def clear_device_offline(self, device_code: str) -> None:
        self.offline_devices.discard(device_code)
