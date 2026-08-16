# store

**Owner:** M1 feat/data-plane
**Design reference:** plans/reports/plan.md $11.4 (Supabase schema, gen_ddl, RPC ingest_batch, outbox)

## Local PostgreSQL with Docker

The local database uses PostgreSQL 16, listens only on
`127.0.0.1:54322`, and initializes a fresh named volume from
`store/schema.sql`.

```bash
docker compose -f store/docker-compose.yml up -d --wait
```

Configure the Python data plane to use the direct local connection:

```bash
export SUPABASE_DB_URL_DIRECT=postgresql://farmops:farmops_dev@127.0.0.1:54322/farmops
python -m store.smoke_test
```

Inspect or stop the database:

```bash
docker compose -f store/docker-compose.yml ps
docker compose -f store/docker-compose.yml logs postgres
docker compose -f store/docker-compose.yml down
```

`down` preserves `vamos-farmops_farmops_postgres_data`. Only use
`docker compose -f store/docker-compose.yml down -v` when intentionally
resetting all local data. Environment variables `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_PORT` override the safe
development defaults.
