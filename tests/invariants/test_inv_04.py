"""INV-4: every decision has >= 1 edge to a real reading; no dangling edge.

Checked at the DB layer against real Postgres (readings_all + edges), since
the edge write path (graph/edges.py, M3 feat/agents) is not merged into dev
yet — this proves the referential-integrity half of INV-4 that the shared
schema/repository layer (store/db.py::append_plan_revision, M1) already
owns; the graph-traversal half is proven separately in M3's own test suite.

Skips when no Postgres is reachable, matching the other live-DB tests.
"""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from contracts import PlanRevision, PlanStatus
from store.db import append_plan_revision, close_pool, get_pool

pytestmark = pytest.mark.invariants


def _run_against_pool(scenario):
    async def main():
        try:
            pool = await get_pool()
        except RuntimeError as error:
            pytest.skip(f"no reachable Postgres for this test: {error}")
        try:
            return await scenario(pool)
        finally:
            await close_pool()

    return asyncio.run(main())


def test_edge_to_a_reading_resolves_to_a_real_row():
    lineage_id = f"pl_inv4_{uuid.uuid4().hex[:8]}"
    revision_id = f"pr_{uuid.uuid4().hex[:8]}"

    async def scenario(pool: asyncpg.Pool) -> tuple[str | None, str | None]:
        async with pool.acquire() as connection:
            reading_id = await connection.fetchval("select id from readings_all limit 1")
            if reading_id is None:
                pytest.skip("no readings present to assert INV-4 against")
            await connection.execute("insert into plans (plan_lineage_id) values ($1)", lineage_id)
        revision = PlanRevision(
            plan_revision_id=revision_id,
            plan_lineage_id=lineage_id,
            version=1,
            status=PlanStatus.PROPOSED,
            created_from_state_version=1,
            evidence_refs=[reading_id],
        )
        edge_id = f"e_inv4_{uuid.uuid4().hex[:8]}"
        await append_plan_revision(
            pool,
            revision,
            edges=[
                {
                    "edge_id": edge_id,
                    "from_type": "plan_revision",
                    "from_id": revision_id,
                    "to_type": "reading",
                    "to_id": reading_id,
                    "relation": "CITES",
                }
            ],
        )
        resolved = await pool.fetchval(
            "select r.id from edges e join readings_all r on r.id = e.to_id where e.edge_id = $1",
            edge_id,
        )
        return edge_id, resolved

    edge_id, resolved = _run_against_pool(scenario)
    assert resolved is not None, f"edge {edge_id} does not resolve to a real reading"


def test_no_dangling_edges_reference_a_nonexistent_reading():
    """Every existing 'reading'-typed edge must resolve. A dangling edge here
    means retention (store/db.py::purge_expired_readings) deleted a reading
    that was still cited, which INV-4 forbids without a compensating delete
    of the edge — this test is the regression guard for that ordering."""

    async def scenario(pool: asyncpg.Pool) -> int:
        return await pool.fetchval(
            "select count(*) from edges e where e.to_type = 'reading' "
            "and not exists (select 1 from readings_all r where r.id = e.to_id)"
        )

    dangling_count = _run_against_pool(scenario)
    assert dangling_count == 0
