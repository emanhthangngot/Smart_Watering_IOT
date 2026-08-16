"""Clock authority, skew correction, and watermark/late tracking.

Design reference: plans/reports/plan.md §3.4. `epoch` is the authority for
event time; `timestamp` is display/cross-check only. A source clock running
wrong makes every reading look permanently fresh or permanently stale, and
the trust engine would be wrong system-wide without anyone noticing — hence
the mismatch audit and the skew correction below.
"""

from __future__ import annotations

import statistics
from collections import deque
from datetime import UTC, datetime

TIME_FIELD_MISMATCH_THRESHOLD_S = 2.0
SKEW_WARN_THRESHOLD_S = 60.0
WATERMARK_LAG_S = 5.0
SKEW_WINDOW = 100


def parse_iso_epoch(timestamp: str) -> float:
    """Parse an ISO-8601 timestamp (as in the payload's `timestamp` field)
    into a Unix epoch (float seconds)."""
    ts = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(ts).timestamp()


def epoch_to_iso(epoch: int | float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ClockTracker:
    """Per-process clock state: skew samples and the ingest watermark."""

    def __init__(self) -> None:
        self._skew_samples: deque[float] = deque(maxlen=SKEW_WINDOW)
        self._max_event_time: float | None = None

    def check_time_field_mismatch(self, epoch: int, timestamp: str | None) -> bool:
        """§3.4: |epoch − parse(timestamp)| > 2s → mismatch, still use epoch."""
        if timestamp is None:
            return False
        try:
            parsed = parse_iso_epoch(timestamp)
        except ValueError:
            return False
        return abs(epoch - parsed) > TIME_FIELD_MISMATCH_THRESHOLD_S

    def record_skew_sample(self, received_at: float, event_time: float) -> None:
        self._skew_samples.append(received_at - event_time)

    def skew_correction(self) -> float:
        """Median of the last 100 (received_at − event_time) samples."""
        if not self._skew_samples:
            return 0.0
        return statistics.median(self._skew_samples)

    def skew_warning(self) -> bool:
        return abs(self.skew_correction()) > SKEW_WARN_THRESHOLD_S

    def compute_age(self, now_server: float, event_time: float) -> tuple[float, bool]:
        """age = now_server − event_time + skew_correction, clamped ≥ 0.

        Returns (age, clock_anomaly) — clock_anomaly is True when the raw
        (pre-clamp) age was negative.
        """
        age = now_server - event_time + self.skew_correction()
        if age < 0:
            return 0.0, True
        return age, False

    def watermark(self) -> float | None:
        if self._max_event_time is None:
            return None
        return self._max_event_time - WATERMARK_LAG_S

    def is_late(self, event_time: float) -> bool:
        """Must be called BEFORE update_watermark for this batch."""
        wm = self.watermark()
        return wm is not None and event_time < wm

    def update_watermark(self, event_time: float) -> None:
        if self._max_event_time is None or event_time > self._max_event_time:
            self._max_event_time = event_time
