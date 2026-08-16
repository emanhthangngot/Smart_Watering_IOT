"""Small additive runtime migration for the live telemetry MVP.

The Docker init script handles a new database. This helper upgrades an
existing local/Supabase database without resetting its volume or data.
"""

from __future__ import annotations

import asyncpg

from store.db import get_pool
from store.gen_ddl import _gen_ingest_batch_rpc, _gen_readings_all_view

_INGEST_BATCH_DDL = """
create table if not exists ingest_batches (
  batch_id            text primary key,
  epoch               bigint not null,
  event_time          timestamptz not null,
  source_received_at  timestamptz not null,
  stored_at           timestamptz not null default now(),
  team_code           text not null,
  environment         text not null,
  scenario            text,
  device_codes        jsonb not null default '[]'::jsonb,
  reading_count       int not null default 0
);
create index if not exists ingest_batches_team_received
  on ingest_batches (team_code, source_received_at desc);
alter table ingest_batches enable row level security;
"""


async def apply_live_ingestion_migration(pool: asyncpg.Pool | None = None) -> None:
    """Idempotently install the batch table, team-scoped view and RPC."""
    target_pool = pool or await get_pool()
    view_sql = _gen_readings_all_view().replace("create view", "create or replace view", 1)
    async with target_pool.acquire() as connection, connection.transaction():
        await connection.execute(_INGEST_BATCH_DDL)
        await connection.execute(view_sql)
        await connection.execute(_gen_ingest_batch_rpc())
