"""Idempotent, allow-listed administrative controls for the causal simulator."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from tools.idempotency import ClaimState, IdempotencyStore, canonical_params, idempotency_key

ALLOWED_SIMULATOR_OPERATIONS = frozenset({"inject-fault", "clear-fault", "reset"})
ALLOWED_SIMULATOR_FAULTS = frozenset(
    {"pump_no_effect", "tank_leak", "sensor_stuck", "device_offline"}
)


class SimulatorAdapter(Protocol):
    def command(self, operation: str, params: Mapping[str, object]) -> Mapping[str, Any]: ...


class SimulatorCommandInProgress(RuntimeError):
    pass


@dataclass(frozen=True)
class SimulatorControlResult:
    delivery_status: str
    data: Mapping[str, Any]


class SimulatorControlGate:
    """Prevents `/sim` from becoming an unapproved irrigation actuator."""

    def __init__(self, adapter: SimulatorAdapter, idempotency: IdempotencyStore) -> None:
        self._adapter = adapter
        self._idempotency = idempotency

    def execute(
        self,
        *,
        operation: str,
        command_id: str,
        params: Mapping[str, object],
    ) -> SimulatorControlResult:
        if operation not in ALLOWED_SIMULATOR_OPERATIONS:
            raise ValueError(f"unsupported simulator control operation: {operation!r}")
        if not command_id.strip():
            raise ValueError("command id is required")
        _validate_operation_params(operation, params)
        request_fingerprint = hashlib.sha256(
            canonical_params({"operation": operation, "params": dict(params)}).encode("utf-8")
        ).hexdigest()
        key = idempotency_key("SIMULATOR-CONTROL", "command", {"commandId": command_id})
        claim = self._idempotency.claim(key)
        if claim.state is ClaimState.COMPLETED:
            envelope = dict(claim.result or {})
            if envelope.get("requestFingerprint") != request_fingerprint:
                raise ValueError(
                    "command id was already used with a different operation or payload"
                )
            stored_result = envelope.get("result")
            if not isinstance(stored_result, Mapping):
                raise ValueError("stored simulator command result is invalid")
            return SimulatorControlResult("DUPLICATE_REPLAY", stored_result)
        if claim.state is ClaimState.IN_PROGRESS:
            raise SimulatorCommandInProgress("simulator command is already in progress")
        result = dict(self._adapter.command(operation, params))
        canonical_params(result)
        self._idempotency.complete(
            key,
            {"requestFingerprint": request_fingerprint, "result": result},
        )
        return SimulatorControlResult("EXECUTED", result)


def _validate_operation_params(operation: str, params: Mapping[str, object]) -> None:
    if operation == "reset":
        if params:
            raise ValueError("reset does not accept parameters")
        return
    fault = params.get("fault")
    if not isinstance(fault, str) or fault not in ALLOWED_SIMULATOR_FAULTS:
        raise ValueError(f"fault must be one of {sorted(ALLOWED_SIMULATOR_FAULTS)}")
