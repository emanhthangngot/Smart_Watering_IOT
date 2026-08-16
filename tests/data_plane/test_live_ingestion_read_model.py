"""Live PostgreSQL coverage for realtime reads and MQTT-outage fallback."""

from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from config import Config
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker
from ingest.presence import PresenceTracker
from ingest.worker import LiveIngestionWorker
from store.db import close_pool, get_pool
from store.ingest import ingest_raw_batch
from store.migrations import apply_live_ingestion_migration
from store.read_model import PostgresFarmStateRepository

pytestmark = pytest.mark.data_plane


def _config(team_code: str, queue_max: int = 128) -> Config:
    return Config(
        team_code=team_code,
        environment="FARM",
        actuation_target="none",
        mqtt_host="",
        mqtt_port=443,
        mqtt_username="",
        mqtt_password="",
        mqtt_client_id="",
        mqtt_topic="",
        supabase_url="",
        supabase_service_role_key="",
        operator_token="",
        mqtt_queue_max=queue_max,
    )


def _batch(config: Config, when: datetime, *, include_soil: bool = True) -> dict:
    devices = [
        {"deviceCode": "PH_01", "status": "ok", "metrics": {"ph": 7.1}},
        {
            "deviceCode": "PUMP_01",
            "status": "ok",
            "metrics": {"flow_rate": 13.9, "power": 646.3},
        },
        {"deviceCode": "SUN_01", "status": "ok", "metrics": {"lux": 49833.3}},
        {"deviceCode": "TANK_01", "status": "ok", "metrics": {"level": 59.8}},
        {
            "deviceCode": "WEATHER_01",
            "status": "ok",
            "metrics": {"temperature": 24.3, "humidity": 66.9},
        },
    ]
    if include_soil:
        devices.append(
            {
                "deviceCode": "SOIL_01",
                "status": "ok",
                "metrics": {"soil_moisture": 36.0, "temperature": 26.1},
            }
        )
    return {
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "epoch": int(when.timestamp()),
        "environment": config.environment,
        "scenario": "NORMAL",
        "devices": devices,
        "teamCode": config.team_code,
    }


async def _cleanup(pool, team_code: str) -> None:
    async with pool.acquire() as connection, connection.transaction():
        for table in (
            "soil_01_readings",
            "weather_01_readings",
            "pump_01_readings",
            "ph_01_readings",
            "tank_01_readings",
            "sun_01_readings",
        ):
            await connection.execute(f"delete from {table} where team_code = $1", team_code)
        await connection.execute("delete from ingest_batches where team_code = $1", team_code)


def test_bounded_worker_drops_oldest_snapshot_observably() -> None:
    worker = LiveIngestionWorker(_config("QUEUE_TEST", queue_max=2))
    worker._offer({"epoch": 1})
    worker._offer({"epoch": 2})
    worker._offer({"epoch": 3})

    status = worker.status()
    assert status["queueDepth"] == 2
    assert status["droppedOverload"] == 1
    assert worker._queue.get_nowait()["epoch"] == 2


def test_postgres_read_model_keeps_last_value_and_marks_it_stale_then_offline() -> None:
    team_code = f"LIVE_{uuid.uuid4().hex[:8]}"
    config = _config(team_code)

    async def scenario() -> None:
        try:
            pool = await get_pool()
        except RuntimeError as error:
            pytest.skip(f"no reachable PostgreSQL: {error}")
        await apply_live_ingestion_migration(pool)
        await _cleanup(pool, team_code)
        clock, cadence, presence = ClockTracker(), CadenceTracker(), PresenceTracker()
        now = datetime.now(UTC).replace(microsecond=100_000)
        baseline = _batch(config, now)
        first, _, written = await ingest_raw_batch(baseline, config, clock, cadence, presence)
        assert written and len(first.readings) == 9

        # Exact MQTT redelivery is idempotent for both rows and batch metadata.
        await ingest_raw_batch(copy.deepcopy(baseline), config, clock, cadence, presence)
        assert (
            await pool.fetchval(
                "select count(*) from ingest_batches where team_code = $1", team_code
            )
            == 1
        )
        assert (
            await pool.fetchval(
                "select count(*) from soil_01_readings where team_code = $1", team_code
            )
            == 1
        )

        repo = PostgresFarmStateRepository(team_code)
        live = await repo.snapshot(now=now + timedelta(seconds=1))
        soil = next(device for device in live["devices"] if device["deviceCode"] == "SOIL_01")
        assert live["ingestion"]["state"] == "LIVE"
        assert soil["metrics"]["soil_moisture"]["state"] == "FRESH"
        assert soil["metrics"]["soil_moisture"]["value"] == 36.0

        outage = await repo.snapshot(now=now + timedelta(seconds=31))
        stale_soil = next(
            device for device in outage["devices"] if device["deviceCode"] == "SOIL_01"
        )
        assert outage["ingestion"]["state"] == "STALE"
        assert stale_soil["metrics"]["soil_moisture"]["state"] == "STALE"
        assert stale_soil["metrics"]["soil_moisture"]["value"] == 36.0

        # Three newer live batches omitting SOIL_01 are device-specific
        # evidence, unlike a stopped whole feed.
        for offset in (2, 3, 4):
            await ingest_raw_batch(
                _batch(config, now + timedelta(seconds=offset), include_soil=False),
                config,
                clock,
                cadence,
                presence,
            )
        offline = await repo.snapshot(now=now + timedelta(seconds=5))
        offline_soil = next(
            device for device in offline["devices"] if device["deviceCode"] == "SOIL_01"
        )
        assert offline["ingestion"]["state"] == "LIVE"
        assert offline_soil["metrics"]["soil_moisture"]["state"] == "OFFLINE"

        await _cleanup(pool, team_code)
        await close_pool()

    asyncio.run(scenario())
