"""Persistence boundary for deterministic trust snapshots."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from trust.score import ScoreSnapshot
from trust.tier import Tier


def snapshot_record(
    snapshot: ScoreSnapshot,
    tier: Tier | str,
    farm_state_version: int | None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Build the exact record shape owned by M1's trust_snapshots table."""
    return {
        "snapshot_id": snapshot_id or f"ts_{uuid4().hex[:12]}",
        "scope": snapshot.scope,
        "dcs": snapshot.dcs,
        "f": snapshot.freshness,
        "c": snapshot.completeness,
        "k": snapshot.consistency,
        "cap_applied": snapshot.cap_applied,
        "tier": str(tier),
        "rules_fired": list(snapshot.rules_fired),
        "dcs_policy_version": snapshot.dcsPolicyVersion,
        "farm_state_version": farm_state_version,
    }


async def persist_snapshot(
    snapshot: ScoreSnapshot,
    tier: Tier | str,
    farm_state_version: int | None,
    snapshot_id: str | None = None,
) -> str:
    """Write one immutable snapshot through M1's shared connection pool."""
    from store.db import get_pool

    record = snapshot_record(snapshot, tier, farm_state_version, snapshot_id)
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            insert into trust_snapshots (
                snapshot_id, scope, dcs, f, c, k, cap_applied, tier,
                rules_fired, dcs_policy_version, farm_state_version
            ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11)
            """,
            record["snapshot_id"],
            record["scope"],
            record["dcs"],
            record["f"],
            record["c"],
            record["k"],
            record["cap_applied"],
            record["tier"],
            json.dumps(record["rules_fired"]),
            record["dcs_policy_version"],
            record["farm_state_version"],
        )
    return str(record["snapshot_id"])
