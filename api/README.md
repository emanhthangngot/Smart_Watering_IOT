# api

**Owner:** M4 feat/tools-runner-api
**Design reference:** plans/reports/plan.md $11.3 (FastAPI app, auth, router auto-discovery)

## Run the live backend

PostgreSQL is the source of truth. MQTT is an optional live write transport;
when it stops, the read API keeps returning the stored last-known values and
marks them `STALE` after their registry TTL.

```bash
python3 -m pip install -r requirements/runtime.txt
docker compose -f store/docker-compose.yml up -d --wait
set -a
. ./.env
set +a
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Useful endpoints:

- `GET /farm/state`: DB-backed devices, metrics, age, TTL and freshness state.
- `GET /health`: PostgreSQL, MQTT, queue, outbox and last-batch health.

Set `MQTT_QUEUE_MAX` to bound snapshots waiting for PostgreSQL. Leaving MQTT
credentials/topic empty disables the subscriber but does not disable DB reads.
Set `CORS_ORIGINS` to the comma-separated frontend origins when deploying away
from the localhost defaults. Run one API worker: multiple Uvicorn workers would
compete for the same MQTT client ID; scale the read API separately only after
extracting ingestion as its own process.
