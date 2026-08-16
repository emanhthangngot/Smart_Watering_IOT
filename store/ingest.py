"""Write path: raw batch → normalize → ingest_batch RPC → ok, or outbox on
failure.

Design reference: plans/reports/plan.md §11.4, §3.2. One RPC call writes
all 6 sensor tables in one transaction; network/timeout failure appends the
already-normalized payload to the local outbox instead of raising — ingest
must never block or lose data on a network blip.

`write_readings` only ever receives already-normalized `Reading`s from
ingest/normalize.py — unknown metrics and non-finite values are dropped
before this module ever sees them (§3.2), so the RPC never has to defend
against malformed data itself.
"""

from __future__ import annotations

import hashlib
import json
import logging

import asyncpg

from config import Config
from contracts import Reading
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker
from ingest.normalize import NormalizeCounters, NormalizeResult, normalize_batch
from ingest.presence import PresenceTracker
from store.db import get_pool
from store.outbox_drain import write_to_outbox

logger = logging.getLogger(__name__)


def _group_by_device(readings: list[Reading]) -> list[dict]:
    """One (id, status, metrics) entry per device — the wide-row shape
    store/schema.sql expects, per §11.4 ("dạng rộng — một hàng mỗi device
    mỗi batch")."""
    by_device: dict[str, dict] = {}
    for r in readings:
        entry = by_device.setdefault(
            r.device_code,
            {
                "deviceCode": r.device_code,
                "id": r.reading_id,
                "status": r.source_status,
                "metrics": {},
            },
        )
        entry["metrics"][r.metric] = r.value
    return list(by_device.values())


async def write_readings(
    readings: list[Reading],
    epoch: int,
    team_code: str,
    scenario: str | None,
    late: bool,
    environment: str = "",
) -> bool:
    """Write already-normalized readings via the `ingest_batch` RPC.

    Returns True if written to Postgres, False if diverted to the outbox
    because of a network/timeout failure. Never raises for network-class
    errors — that is exactly what the outbox exists to absorb.
    """
    if not readings:
        return True

    devices = _group_by_device(readings)
    row_ids = sorted({str(device["id"]) for device in devices})
    batch_identity = json.dumps(
        {"teamCode": team_code, "epoch": epoch, "rowIds": row_ids},
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = {
        "batchId": "b_" + hashlib.sha256(batch_identity.encode()).hexdigest()[:24],
        "epoch": epoch,
        "eventTime": readings[0].event_time,
        "sourceReceivedAt": readings[0].received_at,
        "teamCode": team_code,
        "environment": environment,
        "scenario": scenario,
        "late": late,
        "deviceCodes": [device["deviceCode"] for device in devices],
        "readingCount": len(readings),
        "devices": devices,
    }

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("select ingest_batch($1::jsonb)", json.dumps(payload))
        return True
    except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
        logger.warning("write_readings: database failure, writing to outbox: %s", exc)
        write_to_outbox(payload)
        return False


async def ingest_raw_batch(
    batch: dict,
    config: Config,
    clock: ClockTracker,
    cadence: CadenceTracker,
    presence: PresenceTracker,
    counters: NormalizeCounters | None = None,
) -> tuple[NormalizeResult, NormalizeCounters, bool]:
    """Full write-path entry point: normalize a raw batch, then write it.

    This is the function ingest/mqtt_client.py and sim/publisher.py's
    consumer should call — normalize.py never talks to the DB directly, and
    nothing should call the RPC with unvalidated raw data.
    """
    result, counters = normalize_batch(batch, config, clock, cadence, presence, counters)

    if result.dropped or result.filtered or not result.readings:
        return result, counters, True  # nothing to write is not a write failure

    written = await write_readings(
        result.readings,
        result.epoch,
        config.team_code,
        batch.get("scenario"),
        result.late,
        config.environment,
    )
    return result, counters, written
