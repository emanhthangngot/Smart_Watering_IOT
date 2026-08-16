from __future__ import annotations

from typing import Any

from trust._access import delta, val
from trust.policy import CHANGE_EPSILON

KIND = "soft"
NAME = "soil_rise_pump_off"
PENALTY = 0.15


def rule(bundle: Any, windows: Any) -> bool:
    flow, soil_change = (
        val(bundle, "PUMP_01", "flow_rate"),
        delta(windows, "SOIL_01", "soil_moisture"),
    )
    return (
        flow is not None
        and soil_change is not None
        and flow <= CHANGE_EPSILON
        and soil_change > CHANGE_EPSILON
    )
