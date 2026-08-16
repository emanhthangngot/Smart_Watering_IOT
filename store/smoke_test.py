"""G1 gate: write one real batch, read it back through `readings_all`.

Design reference: plans/reports/plan.md §11.4,
plans/260816-0957-farmops-delivery/phase-05-integration-gates.md (G1).

Usage: python -m store.smoke_test
Requires SUPABASE_DB_URL (or SUPABASE_DB_URL_DIRECT) pointed at a Supabase
project with store/schema.sql already applied. Exits 0 on match, non-zero
otherwise — this is the executable G1 gate, not a judgment call.

Goes through the same normalize → write path as the real MQTT client
(store.ingest.ingest_raw_batch) rather than calling the RPC directly — a
smoke test that bypasses normalize would not catch a break in that wiring.
"""

from __future__ import annotations

import asyncio
import sys
import time

from config import Config
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker
from ingest.presence import PresenceTracker
from registry.specs import SPECS
from store.db import close_pool, get_pool
from store.ingest import ingest_raw_batch


def _make_batch(config: Config, epoch: int) -> dict:
    devices = [
        {
            "deviceCode": "PH_01",
            "status": "ok",
            "metrics": {"ph": 7.2},
        },
        {
            "deviceCode": "PUMP_01",
            "status": "ok",
            "metrics": {"flow_rate": 13.9, "power": 646.3},
        },
        {
            "deviceCode": "SOIL_01",
            "status": "ok",
            "metrics": {"soil_moisture": 36.0, "temperature": 26.1},
        },
        {
            "deviceCode": "SUN_01",
            "status": "ok",
            "metrics": {"lux": 49833.3},
        },
        {
            "deviceCode": "TANK_01",
            "status": "ok",
            "metrics": {"level": 59.8},
        },
        {
            "deviceCode": "WEATHER_01",
            "status": "ok",
            "metrics": {"temperature": 24.3, "humidity": 66.9},
        },
    ]
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(epoch)),
        "epoch": epoch,
        "environment": config.environment,
        "scenario": "NORMAL",
        "devices": devices,
        "teamCode": config.team_code,
    }


async def run() -> int:
    config = Config.from_env()
    epoch = int(time.time())
    batch = _make_batch(config, epoch)

    clock, cadence, presence = ClockTracker(), CadenceTracker(), PresenceTracker()
    result, counters, written = await ingest_raw_batch(batch, config, clock, cadence, presence)
    if result.dropped or result.filtered:
        print(f"smoke_test: FAIL — batch was dropped/filtered: {counters}", file=sys.stderr)
        return 1
    if not written:
        print("smoke_test: FAIL — batch went to outbox, not Postgres", file=sys.stderr)
        return 1

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "select device, metric, value from readings_all "
            "where epoch = $1 order by device, metric",
            epoch,
        )
    await close_pool()

    expected_pairs = {(spec.device_code, spec.metric) for spec in SPECS}
    got_pairs = {(row["device"], row["metric"]) for row in rows}

    missing = expected_pairs - got_pairs
    if missing:
        print(f"smoke_test: FAIL — missing readings for {sorted(missing)}", file=sys.stderr)
        return 1

    devices_written = {row["device"] for row in rows}
    if len(devices_written) != 6:
        print(
            f"smoke_test: FAIL — expected 6 devices, got {len(devices_written)}",
            file=sys.stderr,
        )
        return 1

    print(f"smoke_test: OK — {len(rows)} readings across 6 devices, epoch={epoch}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
