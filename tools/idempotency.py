"""Deterministic keys and an atomic in-memory claim store.

The production store adapter will be supplied by M1.  Keeping the claim API
small makes the safety property explicit: claim happens before a side effect.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


def canonical_params(params: Mapping[str, Any]) -> str:
    """Return stable JSON for idempotency hashing; reject NaN/Infinity."""

    return json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)


def idempotency_key(plan_revision_id: str, tool: str, params: Mapping[str, Any]) -> str:
    material = f"{plan_revision_id}|{tool}|{canonical_params(params)}"
    return hashlib.sha1(material.encode("utf-8"), usedforsecurity=False).hexdigest()


class ClaimState(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class Claim:
    state: ClaimState
    result: Mapping[str, Any] | None = None


class IdempotencyStore(Protocol):
    def claim(self, key: str) -> Claim: ...

    def complete(self, key: str, result: Mapping[str, Any]) -> None: ...

    def abort(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """Thread-safe adapter for tests/local mode; not a persistence substitute."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, Mapping[str, Any] | None] = {}

    def claim(self, key: str) -> Claim:
        with self._lock:
            if key not in self._entries:
                self._entries[key] = None
                return Claim(ClaimState.NEW)
            result = self._entries[key]
            if result is None:
                return Claim(ClaimState.IN_PROGRESS)
            return Claim(ClaimState.COMPLETED, result)

    def complete(self, key: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            if key not in self._entries:
                raise KeyError(f"idempotency key was not claimed: {key}")
            self._entries[key] = dict(result)

    def abort(self, key: str) -> None:
        with self._lock:
            if self._entries.get(key) is None:
                self._entries.pop(key, None)
