"""ingest/normalize.py — §3.2 pipeline behavior under malformed input.
plans/260816-0957-data-plane/phase-03-normalize-and-outbox.md success
criteria.
"""

from __future__ import annotations

import copy

import pytest

from config import Config
from ingest.cadence import CadenceTracker
from ingest.clock import ClockTracker
from ingest.normalize import NormalizeCounters, normalize_batch
from ingest.presence import PresenceTracker


@pytest.fixture
def config():
    return Config(
        team_code="VAMOS",
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
    )


BASE_BATCH = {
    "timestamp": "2026-08-16T02:36:56.448Z",
    "epoch": 1786847816,
    "environment": "FARM",
    "scenario": "NORMAL",
    "devices": [
        {"deviceCode": "PH_01", "status": "ok", "metrics": {"ph": 10}},
        {"deviceCode": "PUMP_01", "status": "ok", "metrics": {"flow_rate": 13.9, "power": 646.3}},
        {
            "deviceCode": "SOIL_01",
            "status": "ok",
            "metrics": {"soil_moisture": 36, "temperature": 26.1},
        },
        {"deviceCode": "SUN_01", "status": "ok", "metrics": {"lux": 49833.3}},
        {"deviceCode": "TANK_01", "status": "ok", "metrics": {"level": 59.8}},
        {
            "deviceCode": "WEATHER_01",
            "status": "ok",
            "metrics": {"temperature": 24.3, "humidity": 66.9},
        },
    ],
    "teamCode": "VAMOS",
}


def _fresh_state():
    return ClockTracker(), CadenceTracker(), PresenceTracker()


@pytest.mark.data_plane
def test_healthy_batch_produces_nine_readings(config):
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(copy.deepcopy(BASE_BATCH), config, clock, cadence, presence)
    assert len(result.readings) == 9
    assert counters.unknown_metric == 0
    assert counters.non_finite == 0
    assert counters.dropped_batches == 0


@pytest.mark.data_plane
def test_same_epoch_subsecond_snapshots_get_distinct_stable_ids(config):
    first = copy.deepcopy(BASE_BATCH)
    second = copy.deepcopy(BASE_BATCH)
    first["timestamp"] = "2026-08-16T03:12:54.438Z"
    second["timestamp"] = "2026-08-16T03:12:54.939Z"
    first["epoch"] = second["epoch"] = 1786849974
    second["devices"][0]["metrics"]["ph"] = 6.9

    first_state = _fresh_state()
    first_result, _ = normalize_batch(first, config, *first_state)
    replay_state = _fresh_state()
    replay_result, _ = normalize_batch(copy.deepcopy(first), config, *replay_state)
    second_state = _fresh_state()
    second_result, _ = normalize_batch(second, config, *second_state)

    first_ids = {reading.reading_id for reading in first_result.readings}
    replay_ids = {reading.reading_id for reading in replay_result.readings}
    second_ids = {reading.reading_id for reading in second_result.readings}
    assert first_ids == replay_ids
    assert first_ids.isdisjoint(second_ids)
    assert first_result.readings[0].event_time.endswith("54.438Z")
    assert second_result.readings[0].event_time.endswith("54.939Z")


@pytest.mark.data_plane
def test_unknown_metric_counted_not_raised(config):
    batch = copy.deepcopy(BASE_BATCH)
    batch["devices"][0]["metrics"]["turbidity"] = 3.2
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert counters.unknown_metric == 1
    assert len(result.readings) == 9  # unknown metric skipped, rest still processed


@pytest.mark.data_plane
@pytest.mark.parametrize(
    "bad_value", [float("nan"), float("inf"), float("-inf"), "not-a-number", True]
)
def test_non_finite_value_counted_not_raised(config, bad_value):
    batch = copy.deepcopy(BASE_BATCH)
    batch["devices"][0]["metrics"]["ph"] = bad_value
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert counters.non_finite == 1
    assert not any(r.device_code == "PH_01" and r.metric == "ph" for r in result.readings)


@pytest.mark.data_plane
def test_missing_both_time_fields_drops_batch(config):
    batch = copy.deepcopy(BASE_BATCH)
    del batch["timestamp"]
    del batch["epoch"]
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert result.dropped is True
    assert counters.dropped_batches == 1
    assert result.readings == []


@pytest.mark.data_plane
def test_invalid_timestamp_without_epoch_drops_batch_instead_of_raising(config):
    batch = copy.deepcopy(BASE_BATCH)
    del batch["epoch"]
    batch["timestamp"] = 12345
    clock, cadence, presence = _fresh_state()

    result, counters = normalize_batch(batch, config, clock, cadence, presence)

    assert result.dropped is True
    assert counters.dropped_batches == 1


@pytest.mark.data_plane
def test_missing_epoch_derives_from_timestamp(config):
    batch = copy.deepcopy(BASE_BATCH)
    del batch["epoch"]
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert result.dropped is False
    assert result.epoch is not None
    assert len(result.readings) == 9


@pytest.mark.data_plane
def test_time_field_mismatch_audited_epoch_still_used(config):
    batch = copy.deepcopy(BASE_BATCH)
    batch["timestamp"] = "2026-08-16T05:16:56.448Z"  # +9600s vs epoch, like the old HOME sample
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert counters.time_field_mismatch == 1
    assert result.epoch == BASE_BATCH["epoch"]
    assert len(result.readings) == 9


@pytest.mark.data_plane
def test_team_or_environment_mismatch_filtered_not_dropped(config):
    batch = copy.deepcopy(BASE_BATCH)
    batch["teamCode"] = "OTHER_TEAM"
    clock, cadence, presence = _fresh_state()
    result, counters = normalize_batch(batch, config, clock, cadence, presence)
    assert result.filtered is True
    assert counters.filtered_batches == 1
    assert result.readings == []


@pytest.mark.data_plane
def test_device_absent_three_consecutive_batches_reports_offline(config):
    clock, cadence, presence = _fresh_state()
    counters = NormalizeCounters()
    for i in range(3):
        batch = copy.deepcopy(BASE_BATCH)
        batch["epoch"] = BASE_BATCH["epoch"] + i * 10
        batch["devices"] = [d for d in batch["devices"] if d["deviceCode"] != "SOIL_01"]
        _, counters = normalize_batch(batch, config, clock, cadence, presence, counters=counters)
    assert presence.is_offline("SOIL_01")
    assert presence.absence_streak("SOIL_01") == 3


@pytest.mark.data_plane
def test_device_absent_once_not_yet_offline(config):
    clock, cadence, presence = _fresh_state()
    batch = copy.deepcopy(BASE_BATCH)
    batch["devices"] = [d for d in batch["devices"] if d["deviceCode"] != "SOIL_01"]
    normalize_batch(batch, config, clock, cadence, presence)
    assert not presence.is_offline("SOIL_01")
    assert presence.absence_streak("SOIL_01") == 1
