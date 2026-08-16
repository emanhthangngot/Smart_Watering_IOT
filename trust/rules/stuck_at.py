from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trust._access import value_bits, values
from trust.policy import STUCK_BATCHES

KIND = "hard"
NAME = "stuck_at"
CORRELATED = {
    "SOIL_01.soil_moisture": ("TANK_01.level", "PUMP_01.flow_rate", "PUMP_01.power"),
    "TANK_01.level": ("PUMP_01.flow_rate", "SOIL_01.soil_moisture"),
    "PUMP_01.flow_rate": ("PUMP_01.power", "TANK_01.level"),
    "PUMP_01.power": ("PUMP_01.flow_rate", "TANK_01.level"),
    "SOIL_01.temperature": ("WEATHER_01.temperature", "SUN_01.lux"),
    "WEATHER_01.temperature": ("SOIL_01.temperature", "SUN_01.lux"),
    "WEATHER_01.humidity": ("WEATHER_01.temperature", "SUN_01.lux"),
    "PH_01.ph": ("TANK_01.level",),
    "SUN_01.lux": ("WEATHER_01.temperature", "WEATHER_01.humidity"),
}


def affected_keys(bundle: Any, windows: Any) -> set[str]:
    del bundle
    if not isinstance(windows, Mapping):
        return set()
    affected: set[str] = set()
    for key in windows:
        if not isinstance(key, str) or "." not in key:
            continue
        bits = value_bits(windows, *key.split(".", 1))
        correlated_moved = any(
            len(other := values(windows, *other_key.split(".", 1))) >= 2 and other[0] != other[-1]
            for other_key in CORRELATED.get(key, ())
        )
        if len(bits) >= STUCK_BATCHES and len(set(bits[-STUCK_BATCHES:])) == 1 and correlated_moved:
            affected.add(key)
    return affected


def rule(bundle: Any, windows: Any) -> bool:
    return bool(affected_keys(bundle, windows))
