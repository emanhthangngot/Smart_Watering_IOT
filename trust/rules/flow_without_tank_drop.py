from __future__ import annotations

from typing import Any

from trust._access import delta, val
from trust.policy import CHANGE_EPSILON, FLOW_MIN

KIND = "soft"
NAME = "flow_without_tank_drop"
PENALTY = 0.25


def rule(bundle: Any, windows: Any) -> bool:
    flow, tank_change = val(bundle, "PUMP_01", "flow_rate"), delta(windows, "TANK_01", "level")
    return (
        flow is not None
        and tank_change is not None
        and flow > FLOW_MIN
        and abs(tank_change) < CHANGE_EPSILON
    )
