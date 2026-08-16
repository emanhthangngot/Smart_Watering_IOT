"""Live-Postgres tests for store/db.py's atomic plan-revision unit and
readings retention (coordination gate C1). Skips when no Postgres is
reachable (pooler/direct/local Docker) so the offline test run stays green.

Bring one up locally with:
    docker compose -f store/docker-compose.yml up -d --wait
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import asyncpg
import pytest

from contracts import PlanRevision, PlanStatus
from store.db import append_plan_revision, close_pool, get_pool, purge_expired_readings

pytestmark = pytest.mark.data_plane


def _run_against_pool(scenario: Callable[[asyncpg.Pool], Coroutine[Any, Any, Any]]) -> Any:
    """Run one test scenario end-to-end (pool acquire → scenario → close) in
    a single event loop; skip if no Postgres tier is reachable."""

    async def main() -> Any:
        try:
            pool = await get_pool()
        except RuntimeError as error:
            pytest.skip(f"no reachable Postgres for this test: {error}")
        try:
            return await scenario(pool)
        finally:
            await close_pool()

    return asyncio.run(main())


def _lineage_id() -> str:
    return f"pl_test_{uuid.uuid4().hex[:8]}"


def test_append_plan_revision_writes_revision_and_edges_atomically():
    lineage_id = _lineage_id()
    revision_id = f"pr_{uuid.uuid4().hex[:8]}"
    edge_id = f"e_{uuid.uuid4().hex[:8]}"

    async def scenario(pool: asyncpg.Pool) -> tuple[Any, Any]:
        async with pool.acquire() as connection:
            await connection.execute("insert into plans (plan_lineage_id) values ($1)", lineage_id)
        revision = PlanRevision(
            plan_revision_id=revision_id,
            plan_lineage_id=lineage_id,
            version=1,
            status=PlanStatus.PROPOSED,
            created_from_state_version=7,
            evidence_refs=["r_abc#tank_level"],
        )
        await append_plan_revision(
            pool,
            revision,
            edges=[
                {
                    "edge_id": edge_id,
                    "from_type": "plan_revision",
                    "from_id": revision_id,
                    "to_type": "evidence",
                    "to_id": "r_abc",
                    "relation": "CITES",
                }
            ],
        )
        row = await pool.fetchrow(
            "select status, created_from_state_version from plan_revisions "
            "where plan_revision_id = $1",
            revision_id,
        )
        edge_row = await pool.fetchrow("select relation from edges where edge_id = $1", edge_id)
        return row, edge_row

    row, edge_row = _run_against_pool(scenario)
    assert row["status"] == "PROPOSED"
    assert row["created_from_state_version"] == 7
    assert edge_row["relation"] == "CITES"


def test_append_plan_revision_rolls_back_edges_on_duplicate_revision_id():
    lineage_id = _lineage_id()
    revision_id = f"pr_{uuid.uuid4().hex[:8]}"
    edge_id = f"e_{uuid.uuid4().hex[:8]}"

    async def scenario(pool: asyncpg.Pool) -> int:
        async with pool.acquire() as connection:
            await connection.execute("insert into plans (plan_lineage_id) values ($1)", lineage_id)
        revision = PlanRevision(
            plan_revision_id=revision_id,
            plan_lineage_id=lineage_id,
            version=1,
            status=PlanStatus.PROPOSED,
            created_from_state_version=7,
        )
        await append_plan_revision(pool, revision)
        with pytest.raises(asyncpg.UniqueViolationError):
            await append_plan_revision(
                pool,
                revision,
                edges=[
                    {
                        "edge_id": edge_id,
                        "from_type": "plan_revision",
                        "from_id": revision_id,
                        "to_type": "evidence",
                        "to_id": "r_should_not_persist",
                        "relation": "CITES",
                    }
                ],
            )
        return await pool.fetchval("select count(*) from edges where edge_id = $1", edge_id)

    assert _run_against_pool(scenario) == 0


def test_purge_expired_readings_deletes_only_old_batches():
    team_code = f"TEST_{uuid.uuid4().hex[:6]}"
    old_epoch = 1
    # Keep the retention test inside an ancient, test-only epoch range. Using
    # the current epoch as cutoff would delete unrelated live demo telemetry
    # from the shared local PostgreSQL volume.
    fresh_epoch = 3

    async def scenario(pool: asyncpg.Pool) -> tuple[int, Any]:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                insert into soil_01_readings
                    (id, epoch, event_time, team_code, source_status, soil_moisture)
                values
                    ($1, $2::bigint, to_timestamp($2::bigint), $5, 'ok', 10),
                    ($3, $4::bigint, to_timestamp($4::bigint), $5, 'ok', 20)
                """,
                f"r_old_{uuid.uuid4().hex[:8]}",
                old_epoch,
                f"r_fresh_{uuid.uuid4().hex[:8]}",
                fresh_epoch,
                team_code,
            )
        deleted = await purge_expired_readings(pool, "soil_01_readings", cutoff_epoch=fresh_epoch)
        remaining = await pool.fetchval(
            "select count(*) from soil_01_readings where team_code = $1", team_code
        )
        return deleted, remaining

    deleted, remaining = _run_against_pool(scenario)
    assert deleted >= 1
    assert remaining == 1


def test_purge_expired_readings_rejects_unknown_table():
    async def scenario(pool: asyncpg.Pool) -> None:
        with pytest.raises(ValueError):
            await purge_expired_readings(pool, "not_a_real_table", cutoff_epoch=0)

    _run_against_pool(scenario)


def test_reserve_active_drawdown_never_double_reserves_under_concurrency():
    from datetime import UTC, datetime

    from store.db import reserve_active_drawdown

    farm_day = datetime.now(UTC).date().isoformat()
    plan_revision_id = f"pr_{uuid.uuid4().hex[:8]}"

    async def scenario(pool: asyncpg.Pool) -> list[bool]:
        await pool.execute(
            "delete from water_ledger where event_time::date = $1",
            datetime.fromisoformat(farm_day).date(),
        )
        results = await asyncio.gather(
            *[
                reserve_active_drawdown(
                    pool,
                    entry_id=f"wl_{uuid.uuid4().hex[:8]}",
                    plan_revision_id=plan_revision_id,
                    action_id=f"act_{i}",
                    requested_drawdown_pct=30,
                    available_drawdown_pct=40,
                    farm_day=farm_day,
                )
                for i in range(5)
            ]
        )
        return list(results)

    accepted = _run_against_pool(scenario)
    # 5 concurrent requests at 30% each against a 40% budget: only one fits.
    assert sum(accepted) == 1


def test_reserve_active_drawdown_accepts_exact_budget():
    from datetime import UTC, datetime

    from store.db import reserve_active_drawdown

    farm_day = datetime.now(UTC).date().isoformat()
    plan_revision_id = f"pr_{uuid.uuid4().hex[:8]}"

    async def scenario(pool: asyncpg.Pool) -> bool:
        await pool.execute(
            "delete from water_ledger where event_time::date = $1",
            datetime.fromisoformat(farm_day).date(),
        )
        return await reserve_active_drawdown(
            pool,
            entry_id=f"wl_{uuid.uuid4().hex[:8]}",
            plan_revision_id=plan_revision_id,
            action_id="act_exact",
            requested_drawdown_pct=40,
            available_drawdown_pct=40,
            farm_day=farm_day,
        )

    assert _run_against_pool(scenario) is True


def test_purge_expired_readings_skips_rows_still_cited_by_an_edge():
    team_code = f"TEST_{uuid.uuid4().hex[:6]}"
    reading_id = f"r_cited_{uuid.uuid4().hex[:8]}"
    old_epoch = 1

    async def scenario(pool: asyncpg.Pool) -> tuple[int, Any]:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                insert into soil_01_readings
                    (id, epoch, event_time, team_code, source_status, soil_moisture)
                values ($1, $2::bigint, to_timestamp($2::bigint), $3, 'ok', 10)
                """,
                reading_id,
                old_epoch,
                team_code,
            )
            await connection.execute(
                """
                insert into edges (edge_id, from_type, from_id, to_type, to_id, relation)
                values ($1, 'plan_revision', 'pr_test', 'reading', $2, 'CITES')
                """,
                f"e_{uuid.uuid4().hex[:8]}",
                reading_id,
            )
        deleted = await purge_expired_readings(pool, "soil_01_readings", cutoff_epoch=2)
        remaining = await pool.fetchval(
            "select count(*) from soil_01_readings where id = $1", reading_id
        )
        return deleted, remaining

    deleted, remaining = _run_against_pool(scenario)
    assert remaining == 1, "a cited reading must not be purged (INV-4)"
