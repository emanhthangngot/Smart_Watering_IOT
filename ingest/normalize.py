"""Batch normalize pipeline: validate → team/env filter → per-device,
per-metric Reading construction → presence tracking.

Design reference: plans/reports/plan.md §3.2. Never crashes on bad input —
unknown metrics, non-finite values, and missing time fields are all
counted, never raised.
"""

from __future__ import annotations

import math
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from config import Config
from contracts import Reading
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker, epoch_to_iso, parse_iso_epoch
from ingest.presence import PresenceTracker
from registry.specs import DEVICES, get_spec


@dataclass
class NormalizeCounters:
    unknown_metric: int = 0
    non_finite: int = 0
    dropped_batches: int = 0
    filtered_batches: int = 0
    time_field_mismatch: int = 0
    clock_anomaly: int = 0
    late_batches: int = 0
    batches_seen: int = 0


@dataclass
class AuditEntry:
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizeResult:
    readings: list[Reading] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
    epoch: int | None = None
    late: bool = False
    dropped: bool = False
    filtered: bool = False


def _reading_id() -> str:
    return "r_" + secrets.token_hex(3)


def _resolve_epoch(batch: dict) -> tuple[int | None, bool]:
    """Return (epoch, had_epoch_field). §3.4: epoch missing → derive from
    timestamp; both missing → None (caller drops the batch)."""
    epoch = batch.get("epoch")
    timestamp = batch.get("timestamp")
    if epoch is not None:
        return int(epoch), True
    if timestamp is not None:
        try:
            return int(round(parse_iso_epoch(timestamp))), False
        except (ValueError, TypeError):
            return None, False
    return None, False


def normalize_batch(
    batch: dict,
    config: Config,
    clock: ClockTracker,
    cadence: CadenceTracker,
    presence: PresenceTracker,
    counters: NormalizeCounters | None = None,
    now_fn: Any = time.time,
) -> tuple[NormalizeResult, NormalizeCounters]:
    """Normalize one raw batch message. Never raises on malformed input."""
    counters = counters or NormalizeCounters()
    counters.batches_seen += 1
    audit: list[AuditEntry] = []

    epoch, had_epoch = _resolve_epoch(batch)
    if epoch is None:
        counters.dropped_batches += 1
        audit.append(AuditEntry("missing_time_fields", {}))
        return NormalizeResult(audit=audit, dropped=True), counters

    devices = batch.get("devices")
    if not isinstance(devices, list):
        counters.dropped_batches += 1
        audit.append(AuditEntry("missing_devices", {}))
        return NormalizeResult(epoch=epoch, audit=audit, dropped=True), counters

    timestamp = batch.get("timestamp")
    if had_epoch and timestamp is not None:
        if clock.check_time_field_mismatch(epoch, timestamp):
            counters.time_field_mismatch += 1
            audit.append(
                AuditEntry(
                    "time_field_mismatch",
                    {"epoch": epoch, "timestamp": timestamp},
                )
            )

    if batch.get("teamCode") != config.team_code or batch.get("environment") != config.environment:
        counters.filtered_batches += 1
        return NormalizeResult(epoch=epoch, filtered=True), counters

    late = clock.is_late(float(epoch))
    if late:
        counters.late_batches += 1
    clock.update_watermark(float(epoch))

    received_at = now_fn()
    clock.record_skew_sample(received_at, float(epoch))
    _, clock_anomaly = clock.compute_age(received_at, float(epoch))
    if clock_anomaly:
        counters.clock_anomaly += 1
        audit.append(AuditEntry("clock_anomaly", {"epoch": epoch}))

    cadence.observe(float(epoch))

    event_time_iso = epoch_to_iso(epoch)
    received_at_iso = epoch_to_iso(received_at)

    readings: list[Reading] = []
    seen_devices: set[str] = set()

    for device in devices:
        device_code = device.get("deviceCode")
        if not device_code:
            continue
        seen_devices.add(device_code)
        presence.mark_present(device_code)
        status = device.get("status", "")
        metrics = device.get("metrics") or {}
        # §3.2: one readingId per device-batch ROW, shared by every metric on
        # that device in this batch — evidenceRefs disambiguate via
        # `{reading_id}#{metric}`. NOT one id per metric.
        row_reading_id = _reading_id()

        for metric, value in metrics.items():
            spec = get_spec(device_code, metric)
            if spec is None:
                counters.unknown_metric += 1
                continue

            if isinstance(value, bool) or not isinstance(value, (int, float)):
                counters.non_finite += 1
                audit.append(
                    AuditEntry(
                        "non_finite_value",
                        {"device": device_code, "metric": metric, "value": repr(value)},
                    )
                )
                continue
            if not math.isfinite(value):
                counters.non_finite += 1
                audit.append(
                    AuditEntry(
                        "non_finite_value",
                        {"device": device_code, "metric": metric, "value": value},
                    )
                )
                continue

            readings.append(
                Reading(
                    reading_id=row_reading_id,
                    device_code=device_code,
                    metric=metric,
                    value=float(value),
                    unit=spec.unit,
                    event_time=event_time_iso,
                    received_at=received_at_iso,
                    batch_epoch=epoch,
                    source_status=status,
                )
            )

    for device_code in DEVICES:
        if device_code not in seen_devices:
            presence.mark_absent(device_code)

    return (
        NormalizeResult(readings=readings, audit=audit, epoch=epoch, late=late),
        counters,
    )
