"""Causal WorldState for `ACTUATION_TARGET=sim` mode.

Design reference: plans/reports/plan.md §9.2,
plans/260816-0957-data-plane/phase-05-simulator.md. One shared state: pump
on moves the tank down AND the soil up together in the same tick, never
independent per-device randomness — otherwise every cross-sensor
consistency rule in §4.3/§5 fires on noise and the trust engine is
meaningless.

Baselines from §3.1 NORMAL observations (fixed values, not fitted).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# NORMAL baselines, plans/reports/plan.md §3.1.
FLOW_BASELINE_L_MIN = 13.9
POWER_BASELINE_W = 646.3
LUX_BASELINE = 49833.3

# Physics rates (per minute of pump-on time). Not competition-measured —
# tuned to produce a visible, monotonic effect within a few ticks.
TANK_DRAIN_PCT_PER_MIN = 1.2
SOIL_RISE_PCT_PER_MIN = 0.8
SOIL_DRY_PCT_PER_MIN = 0.05
TANK_LEAK_PCT_PER_MIN = 0.6


@dataclass
class WorldState:
    tank_level_pct: float = 59.8
    soil_moisture_pct: float = 36.0
    soil_temperature_c: float = 26.1
    weather_temperature_c: float = 24.3
    humidity_pct: float = 66.9
    lux: float = LUX_BASELINE
    ph: float = 10.0

    pump_on: bool = False
    flow_rate_l_min: float = 0.0
    power_w: float = 0.0

    # (device_code, metric) -> frozen value, populated by sim.faults when
    # sensor_stuck activates. tick() overwrites the natural value with this.
    _frozen: dict[tuple[str, str], float] = field(default_factory=dict)

    def freeze(self, device_code: str, metric: str) -> None:
        self._frozen[(device_code, metric)] = self._metric_value(device_code, metric)

    def unfreeze(self, device_code: str, metric: str) -> None:
        self._frozen.pop((device_code, metric), None)

    def _metric_value(self, device_code: str, metric: str) -> float:
        mapping = {
            ("PH_01", "ph"): self.ph,
            ("PUMP_01", "flow_rate"): self.flow_rate_l_min,
            ("PUMP_01", "power"): self.power_w,
            ("SOIL_01", "soil_moisture"): self.soil_moisture_pct,
            ("SOIL_01", "temperature"): self.soil_temperature_c,
            ("SUN_01", "lux"): self.lux,
            ("TANK_01", "level"): self.tank_level_pct,
            ("WEATHER_01", "temperature"): self.weather_temperature_c,
            ("WEATHER_01", "humidity"): self.humidity_pct,
        }
        return mapping[(device_code, metric)]

    def tick(
        self,
        dt_s: float,
        pump_command: bool,
        *,
        pump_no_effect: bool = False,
        tank_leak: bool = False,
    ) -> None:
        """Advance the shared world by dt_s seconds. Pump on moves tank and
        soil together — the causal core the design insists on."""
        dt_min = dt_s / 60.0
        self.pump_on = pump_command

        if self.pump_on:
            self.flow_rate_l_min = FLOW_BASELINE_L_MIN
            self.power_w = POWER_BASELINE_W
        else:
            self.flow_rate_l_min = 0.0
            self.power_w = 0.0

        pump_effective = self.pump_on and not pump_no_effect

        drain = 0.0
        if pump_effective:
            drain += TANK_DRAIN_PCT_PER_MIN * dt_min
        if tank_leak:
            drain += TANK_LEAK_PCT_PER_MIN * dt_min
        self.tank_level_pct = max(0.0, min(100.0, self.tank_level_pct - drain))

        if pump_effective:
            self.soil_moisture_pct += SOIL_RISE_PCT_PER_MIN * dt_min
        else:
            self.soil_moisture_pct -= SOIL_DRY_PCT_PER_MIN * dt_min
        self.soil_moisture_pct = max(0.0, min(100.0, self.soil_moisture_pct))

        for (device_code, metric), frozen_value in self._frozen.items():
            self._set_metric_value(device_code, metric, frozen_value)

    def _set_metric_value(self, device_code: str, metric: str, value: float) -> None:
        if (device_code, metric) == ("PH_01", "ph"):
            self.ph = value
        elif (device_code, metric) == ("PUMP_01", "flow_rate"):
            self.flow_rate_l_min = value
        elif (device_code, metric) == ("PUMP_01", "power"):
            self.power_w = value
        elif (device_code, metric) == ("SOIL_01", "soil_moisture"):
            self.soil_moisture_pct = value
        elif (device_code, metric) == ("SOIL_01", "temperature"):
            self.soil_temperature_c = value
        elif (device_code, metric) == ("SUN_01", "lux"):
            self.lux = value
        elif (device_code, metric) == ("TANK_01", "level"):
            self.tank_level_pct = value
        elif (device_code, metric) == ("WEATHER_01", "temperature"):
            self.weather_temperature_c = value
        elif (device_code, metric) == ("WEATHER_01", "humidity"):
            self.humidity_pct = value

    def metrics_by_device(self) -> dict[str, dict[str, float]]:
        return {
            "PH_01": {"ph": self.ph},
            "PUMP_01": {"flow_rate": self.flow_rate_l_min, "power": self.power_w},
            "SOIL_01": {
                "soil_moisture": self.soil_moisture_pct,
                "temperature": self.soil_temperature_c,
            },
            "SUN_01": {"lux": self.lux},
            "TANK_01": {"level": self.tank_level_pct},
            "WEATHER_01": {
                "temperature": self.weather_temperature_c,
                "humidity": self.humidity_pct,
            },
        }
