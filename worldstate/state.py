"""Immutable, in-memory Farm World State primitives owned by M3."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any


class WorldStateError(Exception):
    """Base error for invalid world-state operations."""


class InvalidStateSection(WorldStateError, ValueError):
    """Raised when an update targets a non-contract top-level section."""


class StateVersionNotFound(WorldStateError, LookupError):
    """Raised when a historical state version is not available."""


_SECTION_NAMES = (
    "telemetry",
    "trust",
    "cross_sensor",
    "resources",
    "active_plan",
    "plans",
    "actions",
    "verifications",
    "inspection_tasks",
    "agent_decisions",
    "trace",
)


def _freeze(value: Any) -> Any:
    """Copy and freeze the small JSON-shaped values used by snapshots."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    raise TypeError(f"unsupported mutable snapshot leaf: {type(value).__name__}")


def _thaw(value: Any) -> Any:
    """Return a mutable copy before applying a copy-on-write update."""

    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_thaw(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class FarmStateSnapshot:
    """One immutable view of the farm state at a monotonically increasing version."""

    state_version: int
    updated_at: datetime
    sections: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.state_version < 0:
            raise ValueError("state version cannot be negative")
        object.__setattr__(self, "sections", _freeze(self.sections))

    @property
    def farm_state_version(self) -> int:
        """Name used by the external JSON contract."""

        return self.state_version

    def section(self, name: str) -> Any:
        """Read one section without exposing mutable state."""

        try:
            return self.sections[name]
        except KeyError as exc:
            raise InvalidStateSection(name) from exc

    def __getattr__(self, name: str) -> Any:
        # Keep the domain record pleasant to use while retaining one canonical
        # immutable section map internally.
        if name in _SECTION_NAMES:
            try:
                return self.sections[name]
            except KeyError as exc:
                raise AttributeError(name) from exc
        raise AttributeError(name)


class WorldState:
    """Copy-on-write state history with explicit timestamps for replay."""

    def __init__(self, initial: Mapping[str, Any] | None = None) -> None:
        initial_values = {name: {} for name in _SECTION_NAMES}
        if initial is not None:
            unknown = set(initial) - set(_SECTION_NAMES)
            if unknown:
                raise InvalidStateSection(sorted(unknown)[0])
            initial_values.update({key: deepcopy(value) for key, value in initial.items()})
        snapshot = FarmStateSnapshot(
            state_version=0,
            updated_at=datetime.min,
            sections=_freeze(initial_values),
        )
        self._history: dict[int, FarmStateSnapshot] = {0: snapshot}

    def current(self) -> FarmStateSnapshot:
        return self._history[max(self._history)]

    def at(self, version: int) -> FarmStateSnapshot:
        try:
            return self._history[version]
        except KeyError as exc:
            raise StateVersionNotFound(version) from exc

    def apply(self, section: str, value: object, *, at: datetime) -> FarmStateSnapshot:
        if section not in _SECTION_NAMES:
            raise InvalidStateSection(section)
        values = {key: _thaw(item) for key, item in self.current().sections.items()}
        values[section] = deepcopy(value)
        next_version = self.current().state_version + 1
        snapshot = FarmStateSnapshot(
            state_version=next_version,
            updated_at=at,
            sections=_freeze(values),
        )
        self._history[next_version] = snapshot
        return snapshot


__all__ = [
    "FarmStateSnapshot",
    "InvalidStateSection",
    "StateVersionNotFound",
    "WorldState",
    "WorldStateError",
]
