---
phase: 2
title: "Supabase schema"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 2: Supabase schema

## Overview

`store/gen_ddl.py` generates `store/schema.sql` from `registry/specs.py`
(6 sensor tables + `readings_all` view + operational tables + `water_ledger`),
RPC `ingest_batch` in one transaction, outbox for network resilience. §11.4.

## Requirements

- Functional: 6 sensor tables (wide form, one row per device per batch),
  `unique(team_code, epoch)`, `on conflict do nothing`; `readings_all` view
  union-alls every (device, metric); RPC `ingest_batch(payload jsonb)`
  writes all 6 tables in one transaction.
- Non-functional: transaction pooler port 6543, `statement_cache_size=0`
  for asyncpg; RLS on, `anon` no write; outbox JSONL survives network drop.

## Architecture

`store/schema.sql` is **generated, never hand-edited** — `store/gen_ddl.py`
reads `registry/specs.py` so schema and registry can never drift apart
(§16 risk). Ingest path: batch → normalize → `ingest_batch` RPC → ok, or
network failure → outbox JSONL, drained later, `on conflict do nothing`
makes replay idempotent.

## Related Code Files

- Create: `store/gen_ddl.py`, `store/schema.sql` (generated output),
  `store/db.py` (connection pool), `store/ingest.py` (RPC call + outbox
  fallback), `store/outbox_drain.py`, `store/smoke_test.py` (G1 gate script)

## Implementation Steps

1. `store/gen_ddl.py`: read `registry/specs.py`, emit 6 `create table`
   statements (shared columns + per-device metric columns) + `readings_all`
   view + operational tables (`plans`, `plan_revisions`, `assumptions`,
   `challenges`, `approvals`, `actions`, `verifications`, `edges`,
   `water_ledger`, `inspection_tasks`, `notifications`, `audit_log`,
   `trust_snapshots`).
2. Apply `store/schema.sql` to the Supabase project (SQL editor or CLI).
3. Write `store/db.py`: asyncpg pool via pooler `:6543`, `statement_cache_size=0`.
4. Write `store/ingest.py`: `ingest_batch` RPC call; on network error, append
   to `store/outbox/*.jsonl` instead of raising.
5. Write `store/outbox_drain.py`: background task replaying outbox in order.
6. Write `store/smoke_test.py`: writes one real batch, reads back via
   `readings_all`, exits 0 on match — this is the G1 gate command.

## Success Criteria

- [ ] `python -m store.smoke_test` writes 6 rows and reads them back via `readings_all`.
- [ ] Duplicate batch (same `team_code, epoch`) via `ingest_batch` produces no duplicate rows.
- [ ] Simulated network failure writes to outbox, not lost; drain later succeeds.
- [ ] `store/schema.sql` header states it is generated — never hand-edit note.

## Risk Assessment

Supabase pooler port 6543 may be blocked at the venue network (§18 open
question 8). Mitigation already in design: fall back to port 5432 (session
mode, re-enable prepared statements) — implement both paths behind config.

## 2026-08-16 live-feed correction

The captured FARM feed publishes about every 500 ms while `epoch` has only
whole-second precision. Therefore `(team_code, epoch)` cannot be the unique
key: it would discard nearly half of valid snapshots. Each device-row now has
a deterministic content-derived primary key, RPC replay conflicts on `id`,
and `(team_code, epoch desc)` remains a non-unique query index. A timestamp
that agrees with the authoritative epoch contributes sub-second event-time
precision; a mismatched timestamp is still audited and ignored.
