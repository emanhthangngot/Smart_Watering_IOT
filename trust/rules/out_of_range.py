from __future__ import annotations

from typing import Any

from trust._access import val

KIND = "hard"
NAME = "out_of_range"

BOUNDS = {
    ("PH_01", "ph"): (0.0, 14.0),
    ("SOIL_01", "soil_moisture"): (0.0, 100.0),
    ("TANK_01", "level"): (0.0, 100.0),
    ("PUMP_01", "flow_rate"): (0.0, None),
    ("SUN_01", "lux"): (0.0, None),
}


def rule(bundle: Any, windows: Any) -> bool:
    del windows
    return any(
        value is not None
        and (lower is not None and value < lower or upper is not None and value > upper)
        for (device, metric), (lower, upper) in BOUNDS.items()
        for value in [val(bundle, device, metric)]
    )
