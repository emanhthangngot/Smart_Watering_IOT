"""Supabase Postgres connection pool.

Design reference: plans/reports/plan.md §11.4. Uses the transaction pooler
(port 6543) by default for the many-small-write ingest load; falls back to
the direct/session port (5432) if the pooler is blocked at the venue
network (§18 open question 8) — both paths behind config, per phase-02's
risk mitigation.

Connection strings are read directly from the environment here rather than
through config.py: config.py is dev-owned (CODEOWNERS) and does not carry a
Postgres DSN field, only the Supabase project URL/service key used by other
branches for REST access. Document new keys in your own .env.example block,
never edit config.py from this branch.
"""

from __future__ import annotations

import os

import asyncpg

# Transaction pooler, port 6543 — no prepared statements, hence
# statement_cache_size=0 below.
POOLER_DSN_ENV = "SUPABASE_DB_URL"
# Session mode, port 5432 — prepared statements re-enabled. Fallback only.
DIRECT_DSN_ENV = "SUPABASE_DB_URL_DIRECT"

_pool: asyncpg.Pool | None = None


async def get_pool(min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Return the process-wide connection pool, creating it on first use.

    Tries the transaction pooler first; if that DSN is absent or the
    connection fails, falls back to the direct/session DSN.
    """
    global _pool
    if _pool is not None:
        return _pool

    pooler_dsn = os.environ.get(POOLER_DSN_ENV)
    direct_dsn = os.environ.get(DIRECT_DSN_ENV)

    if pooler_dsn:
        try:
            _pool = await asyncpg.create_pool(
                dsn=pooler_dsn,
                min_size=min_size,
                max_size=max_size,
                statement_cache_size=0,
            )
            return _pool
        except (OSError, asyncpg.PostgresError):
            if not direct_dsn:
                raise

    if direct_dsn:
        _pool = await asyncpg.create_pool(
            dsn=direct_dsn,
            min_size=min_size,
            max_size=max_size,
        )
        return _pool

    raise RuntimeError(
        f"No Supabase DSN configured — set {POOLER_DSN_ENV} (preferred, port "
        f"6543) or {DIRECT_DSN_ENV} (fallback, port 5432) in .env."
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
