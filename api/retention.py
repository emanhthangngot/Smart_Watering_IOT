"""Retention orchestration port; M1 supplies the transaction implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

RETENTION_BATCH_SIZE = 5_000


class RetentionPort(Protocol):
    def rollup_before(self, cutoff: datetime) -> None: ...

    def delete_sensor_batch(self, cutoff: datetime, limit: int) -> int: ...


def run_retention(port: RetentionPort, cutoff: datetime, *, max_batches: int = 100) -> int:
    """Roll up first, then delete bounded sensor batches only."""

    if cutoff.tzinfo is None:
        raise ValueError("retention cutoff must be timezone-aware")
    if max_batches <= 0:
        raise ValueError("max_batches must be positive")
    port.rollup_before(cutoff)
    deleted = 0
    for _ in range(max_batches):
        count = port.delete_sensor_batch(cutoff, RETENTION_BATCH_SIZE)
        if count < 0 or count > RETENTION_BATCH_SIZE:
            raise ValueError("retention port returned an invalid batch count")
        deleted += count
        if count < RETENTION_BATCH_SIZE:
            break
    return deleted
