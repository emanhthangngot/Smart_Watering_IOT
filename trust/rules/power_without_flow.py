from __future__ import annotations

from typing import Any

from trust._access import val
from trust.policy import CHANGE_EPSILON, POWER_HIGH

KIND = "soft"
NAME = "power_without_flow"
PENALTY = 0.30


def rule(bundle: Any, windows: Any) -> bool:
    power, flow = val(bundle, "PUMP_01", "power"), val(bundle, "PUMP_01", "flow_rate")
    return power is not None and flow is not None and power > POWER_HIGH and flow <= CHANGE_EPSILON
