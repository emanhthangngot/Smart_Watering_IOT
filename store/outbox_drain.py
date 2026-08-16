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
import os
import threading
from pathlib import Path

import asyncpg

from store.db import get_pool

logger = logging.getLogger(__name__)

OUTBOX_DIR = Path(__file__).with_name("outbox")
OUTBOX_FILE = OUTBOX_DIR / "pending.jsonl"

DRAIN_INTERVAL_S = 10
_FILE_LOCK = threading.Lock()


def _draining_file() -> Path:
    return OUTBOX_FILE.with_name(f"{OUTBOX_FILE.name}.draining")


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line.strip()]


def write_to_outbox(payload: dict) -> None:
    with _FILE_LOCK:
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        with OUTBOX_FILE.open("a") as f:
            f.write(json.dumps(payload) + "\n")


def outbox_depth() -> int:
    """Number of pending batches — surfaced on /health per §11.4."""
    with _FILE_LOCK:
        return len(_lines(OUTBOX_FILE)) + len(_lines(_draining_file()))


async def drain_once() -> int:
    """Replay the outbox in order. Stops at the first failure so ordering
    and at-least-once delivery are preserved; returns the number drained.
    """
    draining_file = _draining_file()
    # Atomically detach the current queue. New failures append to a fresh
    # pending file while this immutable segment is replayed.
    with _FILE_LOCK:
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        if not draining_file.exists() and OUTBOX_FILE.exists():
            os.replace(OUTBOX_FILE, draining_file)
        lines = _lines(draining_file)
    if not lines:
        with _FILE_LOCK:
            if draining_file.exists():
                draining_file.unlink()
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

    with _FILE_LOCK:
        newly_queued = _lines(OUTBOX_FILE)
        if remaining:
            # Failed old entries must stay before batches that arrived while
            # replay was in flight. Replace atomically so a crash yields at
            # worst an idempotent duplicate, never a lost batch.
            merged = remaining + newly_queued
            temp_file = OUTBOX_FILE.with_name(f".{OUTBOX_FILE.name}.merge.tmp")
            temp_file.write_text("\n".join(merged) + "\n")
            os.replace(temp_file, OUTBOX_FILE)
        if draining_file.exists():
            draining_file.unlink()

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
