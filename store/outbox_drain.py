"""Local outbox for network resilience — append-only JSONL, drained in order.

Design reference: plans/reports/plan.md §11.4. The outbox is not a second
source of truth; it is an empty queue under normal conditions. `on conflict
do nothing` (via the `ingest_batch` RPC) makes replaying it idempotent, so
draining out of order or twice is harmless — draining is still done in
order for auditability.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import asyncpg

from store.db import get_pool

logger = logging.getLogger(__name__)

OUTBOX_DIR = Path(__file__).with_name("outbox")
OUTBOX_FILE = OUTBOX_DIR / "pending.jsonl"

DRAIN_INTERVAL_S = 10


def write_to_outbox(payload: dict) -> None:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    with OUTBOX_FILE.open("a") as f:
        f.write(json.dumps(payload) + "\n")


def outbox_depth() -> int:
    """Number of pending batches — surfaced on /health per §11.4."""
    if not OUTBOX_FILE.exists():
        return 0
    with OUTBOX_FILE.open() as f:
        return sum(1 for line in f if line.strip())


async def drain_once() -> int:
    """Replay the outbox in order. Stops at the first failure so ordering
    and at-least-once delivery are preserved; returns the number drained.
    """
    if not OUTBOX_FILE.exists():
        return 0

    lines = [line for line in OUTBOX_FILE.read_text().splitlines() if line.strip()]
    if not lines:
        return 0

    pool = await get_pool()
    drained = 0
    remaining = list(lines)

    for line in lines:
        payload = json.loads(line)
        try:
            async with pool.acquire() as conn:
                await conn.execute("select ingest_batch($1::jsonb)", json.dumps(payload))
            drained += 1
            remaining.pop(0)
        except (OSError, asyncpg.exceptions.PostgresConnectionError, TimeoutError) as exc:
            logger.warning("outbox drain: still failing, stopping this pass: %s", exc)
            break

    if remaining:
        OUTBOX_FILE.write_text("\n".join(remaining) + "\n")
    else:
        OUTBOX_FILE.write_text("")

    return drained


async def drain_forever(interval_s: int = DRAIN_INTERVAL_S) -> None:
    """Background task: replay the outbox on a fixed interval."""
    while True:
        try:
            drained = await drain_once()
            if drained:
                logger.info("outbox drain: replayed %d batch(es)", drained)
        except Exception:
            logger.exception("outbox drain: unexpected error, will retry next tick")
        await asyncio.sleep(interval_s)
