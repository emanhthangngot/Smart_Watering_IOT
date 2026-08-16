from __future__ import annotations

from typing import Any

from trust._access import delta, val
from trust.policy import CHANGE_EPSILON

KIND = "soft"
NAME = "tank_drain_no_pump"
PENALTY = 0.30


def rule(bundle: Any, windows: Any) -> bool:
    flow, tank_change = val(bundle, "PUMP_01", "flow_rate"), delta(windows, "TANK_01", "level")
    return (
        flow is not None
        and tank_change is not None
        and flow <= CHANGE_EPSILON
        and tank_change < -CHANGE_EPSILON
    )
