"""INV-8: supported actuation targets are observation-only or simulator."""

import pytest

from api.simulator import SimulatorControlGate
from schedule.runner import NoActuation, actuator_for
from tools.idempotency import InMemoryIdempotencyStore

pytestmark = pytest.mark.invariants


def test_no_real_hardware_target_exists() -> None:
    assert isinstance(actuator_for("none"), NoActuation)
    with pytest.raises(ValueError):
        actuator_for("real")
    with pytest.raises(ValueError):
        actuator_for("hardware")
    with pytest.raises(ValueError):
        actuator_for("sim")


def test_public_simulator_control_cannot_start_or_stop_a_pump() -> None:
    class Adapter:
        def __init__(self) -> None:
            self.calls = []

        def command(self, operation, params):
            self.calls.append((operation, params))
            return {"status": "ACCEPTED"}

    adapter = Adapter()
    gate = SimulatorControlGate(adapter, InMemoryIdempotencyStore())
    for operation in ("pump-start", "pump-stop", "hardware"):
        with pytest.raises(ValueError):
            gate.execute(operation=operation, command_id="cmd-1", params={})
    assert adapter.calls == []
