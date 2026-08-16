"""Device presence tracker — absence from `devices[]` is the OFFLINE signal.

Design reference: plans/reports/plan.md §3.1 point 3, §3.3. A device
missing from the batch array is a real signal at `scenario: NORMAL` (all 6
devices are always present), not "hasn't published yet".
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_OFFLINE_BATCHES = 3


@dataclass
class PresenceTracker:
    offline_batches: int = DEFAULT_OFFLINE_BATCHES
    _consecutive_absences: dict[str, int] = field(default_factory=dict)
    _ever_seen: set[str] = field(default_factory=set)

    def mark_present(self, device_code: str) -> None:
        self._consecutive_absences[device_code] = 0
        self._ever_seen.add(device_code)

    def mark_absent(self, device_code: str) -> int:
        """Increment the absence streak, return the new streak length."""
        streak = self._consecutive_absences.get(device_code, 0) + 1
        self._consecutive_absences[device_code] = streak
        return streak

    def is_offline(self, device_code: str) -> bool:
        return self._consecutive_absences.get(device_code, 0) >= self.offline_batches

    def is_missing(self, device_code: str) -> bool:
        """Never once observed — distinct from OFFLINE (§3.3)."""
        return device_code not in self._ever_seen

    def absence_streak(self, device_code: str) -> int:
        return self._consecutive_absences.get(device_code, 0)
