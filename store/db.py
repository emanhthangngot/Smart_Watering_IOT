"""Supabase Postgres connection pool, with a local Docker fallback.

Design reference: plans/reports/plan.md §11.4. Uses the transaction pooler
(port 6543) by default for the many-small-write ingest load; falls back to
the direct/session port (5432) if the pooler is blocked at the venue
network (§18 open question 8), and finally to the local Docker PostgreSQL
compose stack (`store/docker-compose.yml`) for offline/local development —
all three paths behind config, per phase-02's risk mitigation.

Connection strings are read directly from the environment here rather than
through config.py: config.py is dev-owned (CODEOWNERS) and does not carry a
Postgres DSN field, only the Supabase project URL/service key used by other
branches for REST access. Document new keys in your own .env.example block,
never edit config.py from this branch.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import date

import asyncpg

from contracts import PlanRevision

# Transaction pooler, port 6543 — no prepared statements, hence
# statement_cache_size=0 below.
POOLER_DSN_ENV = "SUPABASE_DB_URL"
# Session mode, port 5432 — prepared statements re-enabled. Fallback only.
DIRECT_DSN_ENV = "SUPABASE_DB_URL_DIRECT"
# Optional override for the local Docker compose stack; defaults to the
# credentials baked into store/docker-compose.yml so `docker compose -f
# store/docker-compose.yml up -d --wait` works with zero extra config.
LOCAL_DSN_ENV = "LOCAL_POSTGRES_DSN"
LOCAL_DOCKER_DSN_DEFAULT = "postgresql://farmops:farmops_dev@127.0.0.1:54322/farmops"

_pool: asyncpg.Pool | None = None


async def get_pool(min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Return the process-wide connection pool, creating it on first use.

    Tries, in order: the transaction pooler, the direct/session DSN, then
    the local Docker compose Postgres. Each tier is skipped silently on
    connection failure so a laptop with no cloud credentials still works
    against `docker compose -f store/docker-compose.yml up -d --wait`.
    """
    global _pool
    if _pool is not None:
        return _pool

    candidates: list[tuple[str, dict]] = []
    if pooler_dsn := os.environ.get(POOLER_DSN_ENV):
        candidates.append((pooler_dsn, {"statement_cache_size": 0}))
    if direct_dsn := os.environ.get(DIRECT_DSN_ENV):
        candidates.append((direct_dsn, {}))
    local_dsn = os.environ.get(LOCAL_DSN_ENV, LOCAL_DOCKER_DSN_DEFAULT)
    candidates.append((local_dsn, {}))

    last_error: Exception | None = None
    for dsn, extra_kwargs in candidates:
        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn, min_size=min_size, max_size=max_size, **extra_kwargs
            )
            return _pool
        except (OSError, asyncpg.PostgresError) as error:
            last_error = error
            continue

    raise RuntimeError(
        f"No reachable Postgres — tried {POOLER_DSN_ENV}, {DIRECT_DSN_ENV}, and "
        f"the local Docker compose stack ({LOCAL_DSN_ENV} or the default "
        f"{LOCAL_DOCKER_DSN_DEFAULT!r}). Set one of those env vars, or start "
        f"`docker compose -f store/docker-compose.yml up -d --wait`."
    ) from last_error


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def append_plan_revision(
    pool: asyncpg.Pool,
    plan_revision: PlanRevision,
    *,
    assumption_ids: Iterable[str] = (),
    edges: Iterable[Mapping[str, str]] = (),
) -> None:
    """Insert one plan revision plus its assumption links and graph edges as
    a single atomic unit (coordination gate C1).

    ``edges`` items need ``edge_id``, ``from_type``, ``from_id``, ``to_type``,
    ``to_id``, ``relation`` keys, matching the ``edges`` table shape.
    Assumptions referenced by ``assumption_ids`` must already exist — this
    function only records that this revision cites them via
    ``plan_revisions.assumptions``; it does not create assumption rows.
    """
    payload = asdict(plan_revision)
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """
            insert into plan_revisions (
                plan_revision_id, plan_lineage_id, version,
                revision_of_plan_revision_id, status, goal,
                created_from_state_version, evidence_refs, constraints,
                assumptions, actions, expected_outcomes, water_budget,
                confidence, requires_approval, challenges, decision_log
            ) values (
                $1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9::jsonb,
                $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb,
                $15, $16::jsonb, $17::jsonb
            )
            """,
            payload["plan_revision_id"],
            payload["plan_lineage_id"],
            payload["version"],
            payload["revision_of_plan_revision_id"],
            str(payload["status"]),
            json.dumps(payload["goal"]),
            payload["created_from_state_version"],
            json.dumps(payload["evidence_refs"]),
            json.dumps(payload["constraints"]),
            json.dumps(list(assumption_ids)),
            json.dumps(payload["actions"]),
            json.dumps(payload["expected_outcomes"]),
            json.dumps(payload["water_budget"]),
            json.dumps(payload["confidence"]),
            payload["requires_approval"],
            json.dumps(payload["challenges"]),
            json.dumps(payload["decision_log"]),
        )
        for edge in edges:
            await connection.execute(
                """
                insert into edges (edge_id, from_type, from_id, to_type, to_id, relation)
                values ($1, $2, $3, $4, $5, $6)
                on conflict (edge_id) do nothing
                """,
                edge["edge_id"],
                edge["from_type"],
                edge["from_id"],
                edge["to_type"],
                edge["to_id"],
                edge["relation"],
            )


async def purge_expired_readings(
    pool: asyncpg.Pool, table: str, cutoff_epoch: int, *, batch_size: int = 5000
) -> int:
    """Delete rows older than ``cutoff_epoch`` in small batches (plan.md
    §11.4 retention: ``delete ... where epoch < $1 limit 5000``), so a long
    retention sweep never holds one long lock against the ingest path.

    Never deletes a row still cited by an ``edges`` row (INV-4: every
    decision-edge to a reading must keep resolving to a real row) — a
    cited-but-expired reading is skipped, not force-deleted, and stays
    until whatever cites it is itself retired.

    ``table`` must be one of the generated `*_readings` tables; validated
    against a fixed allowlist to keep this a parameterized query, not string
    interpolation of caller-controlled SQL identifiers.
    """
    allowed_tables = {
        "soil_01_readings",
        "weather_01_readings",
        "pump_01_readings",
        "ph_01_readings",
        "tank_01_readings",
        "sun_01_readings",
    }
    if table not in allowed_tables:
        raise ValueError(f"unknown readings table: {table!r}")
    deleted = 0
    async with pool.acquire() as connection:
        while True:
            result = await connection.execute(
                f"""
                delete from {table} where id in (
                    select id from {table}
                    where epoch < $1
                    and not exists (
                        select 1 from edges e
                        where e.to_type = 'reading' and e.to_id = {table}.id
                    )
                    limit $2
                )
                """,
                cutoff_epoch,
                batch_size,
            )
            count = int(result.split()[-1]) if result else 0
            deleted += count
            if count < batch_size:
                break
    return deleted


async def reserve_active_drawdown(
    pool: asyncpg.Pool,
    *,
    entry_id: str,
    plan_revision_id: str,
    action_id: str,
    requested_drawdown_pct: float,
    available_drawdown_pct: float,
    farm_day: str,
) -> bool:
    """Atomically accept or reject one drawdown reservation against the
    active total for ``farm_day`` (coordination gate C3).

    A Postgres transaction-scoped advisory lock keyed by ``farm_day``
    serializes concurrent callers reserving against the same day, so the
    check-then-insert below cannot race: two concurrent reservations can
    never both pass when only one fits the remaining budget. A reservation
    is a ``water_ledger`` row with ``actual_drawdown_pct`` still null; M4's
    runner fills in ``actual_drawdown_pct`` when the schedule closes.

    Returns ``True`` and inserts the reservation row, or ``False`` and
    inserts nothing, when ``active_reserved + requested > available``.
    """
    farm_day_date = date.fromisoformat(farm_day)
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute("select pg_advisory_xact_lock(hashtext($1))", farm_day)
        active_reserved = await connection.fetchval(
            "select coalesce(sum(planned_drawdown_pct), 0) from water_ledger "
            "where event_time::date = $1 and actual_drawdown_pct is null",
            farm_day_date,
        )
        if float(active_reserved) + requested_drawdown_pct > available_drawdown_pct:
            return False
        await connection.execute(
            """
            insert into water_ledger
                (entry_id, plan_revision_id, action_id, planned_drawdown_pct, event_time)
            values ($1, $2, $3, $4, now())
            """,
            entry_id,
            plan_revision_id,
            action_id,
            requested_drawdown_pct,
        )
        return True
