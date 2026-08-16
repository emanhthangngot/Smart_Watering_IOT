"""Pure invalidation selection and local storm-protection guard."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class InvalidationKey:
    plan_revision_id: str
    assumption_id: str
    triggering_evidence_version: int


@dataclass(frozen=True, slots=True)
class InvalidationDecision:
    key: InvalidationKey
    reason: str
    observed_at: datetime


def select_touched_assumptions(
    changed_keys: Iterable[str], dependency_index: Mapping[str, Iterable[str]]
) -> tuple[str, ...]:
    changed = set(changed_keys)
    return tuple(
        sorted(
            assumption_id
            for assumption_id, dependencies in dependency_index.items()
            if changed & set(dependencies)
        )
    )


def evaluate_changes(
    changed_keys: Iterable[str],
    dependency_index: Mapping[str, Iterable[str]],
    *,
    now: datetime,
    evaluator: Callable[[str, frozenset[str], datetime], InvalidationDecision | None],
) -> tuple[InvalidationDecision, ...]:
    changed = frozenset(changed_keys)
    decisions: list[InvalidationDecision] = []
    for assumption_id in select_touched_assumptions(changed, dependency_index):
        decision = evaluator(assumption_id, changed, now)
        if decision is not None:
            decisions.append(decision)
    return tuple(decisions)


class InvalidationGuard:
    """Process-local fast path; C1 remains authoritative across restart."""

    def __init__(self, *, debounce: timedelta, max_entries: int = 10_000) -> None:
        if debounce <= timedelta(0) or max_entries <= 0:
            raise ValueError("debounce and max_entries must be positive")
        self._debounce = debounce
        self._max_entries = max_entries
        self._seen: dict[InvalidationKey, datetime] = {}
        self._highest_version_by_slot: dict[tuple[str, str], int] = {}
        self._last_by_slot: dict[tuple[str, str], datetime] = {}
        self._open_replans: set[tuple[str, str]] = set()

    def accept(self, decision: InvalidationDecision) -> bool:
        key = decision.key
        slot = (key.plan_revision_id, key.assumption_id)
        highest_version = self._highest_version_by_slot.get(slot)
        if (
            key in self._seen
            or (highest_version is not None and key.triggering_evidence_version <= highest_version)
            or slot in self._open_replans
        ):
            return False
        previous = self._last_by_slot.get(slot)
        if previous is not None and decision.observed_at - previous < self._debounce:
            return False
        self._seen[key] = decision.observed_at
        self._highest_version_by_slot[slot] = key.triggering_evidence_version
        self._last_by_slot[slot] = decision.observed_at
        self._open_replans.add(slot)
        self._trim()
        return True

    def close_replan(self, plan_revision_id: str, assumption_id: str) -> None:
        self._open_replans.discard((plan_revision_id, assumption_id))

    def cleanup(self, *, now: datetime) -> None:
        cutoff = now - self._debounce
        self._seen = {key: seen_at for key, seen_at in self._seen.items() if seen_at >= cutoff}
        self._last_by_slot = {
            slot: seen_at
            for slot, seen_at in self._last_by_slot.items()
            if seen_at >= cutoff or slot in self._open_replans
        }
        live_slots = set(self._last_by_slot) | self._open_replans
        self._highest_version_by_slot = {
            slot: version
            for slot, version in self._highest_version_by_slot.items()
            if slot in live_slots
        }
        self._trim()

    def _trim(self) -> None:
        if len(self._seen) <= self._max_entries:
            return
        oldest = sorted(self._seen, key=self._seen.__getitem__)[
            : len(self._seen) - self._max_entries
        ]
        for key in oldest:
            self._seen.pop(key, None)

    @property
    def open_replans(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._open_replans)

    @property
    def remembered_events(self) -> int:
        return len(self._seen)


__all__ = [
    "InvalidationDecision",
    "InvalidationGuard",
    "InvalidationKey",
    "evaluate_changes",
    "select_touched_assumptions",
]
