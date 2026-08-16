"""sim/ — causal WorldState simulator. plans/reports/plan.md §9.2,
plans/260816-0957-data-plane/phase-05-simulator.md success criteria.
"""

from __future__ import annotations

import pytest

from config import Config
from sim.faults import FaultFlags
from sim.publisher import DEVICE_ORDER, build_batch
from sim.world import WorldState


@pytest.fixture
def config():
    return Config(
        team_code="VAMOS",
        environment="FARM",
        actuation_target="sim",
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


@pytest.mark.data_plane
def test_pump_on_moves_tank_down_and_soil_up_together():
    world = WorldState()
    tank0, soil0 = world.tank_level_pct, world.soil_moisture_pct
    for _ in range(10):
        world.tick(60, True)
    assert world.tank_level_pct < tank0
    assert world.soil_moisture_pct > soil0


@pytest.mark.data_plane
def test_pump_off_does_not_drain_tank():
    world = WorldState()
    tank0 = world.tank_level_pct
    for _ in range(5):
        world.tick(60, False)
    assert world.tank_level_pct == tank0


@pytest.mark.data_plane
def test_sensor_stuck_freezes_one_metric_while_others_move():
    world = WorldState()
    faults = FaultFlags()
    faults.set_sensor_stuck(world, "SOIL_01", "soil_moisture")

    values = []
    for _ in range(12):
        world.tick(60, True, pump_no_effect=False, tank_leak=False)
        values.append(world.soil_moisture_pct)

    assert len(set(values)) == 1  # bit-identical across >=12 batches
    assert world.tank_level_pct < 59.8  # TANK_01 still moves


@pytest.mark.data_plane
def test_device_offline_flag_removes_device_from_batch(config):
    world = WorldState()
    faults = FaultFlags()
    faults.set_device_offline("SOIL_01")

    batch = build_batch(world, faults, config, epoch=1_700_000_000)
    device_codes = {d["deviceCode"] for d in batch["devices"]}
    assert "SOIL_01" not in device_codes
    assert device_codes == set(DEVICE_ORDER) - {"SOIL_01"}


@pytest.mark.data_plane
def test_batch_shape_matches_real_payload(config):
    world = WorldState()
    faults = FaultFlags()
    batch = build_batch(world, faults, config, epoch=1_700_000_000)

    assert set(batch.keys()) == {
        "timestamp",
        "epoch",
        "environment",
        "scenario",
        "devices",
        "teamCode",
    }
    for device in batch["devices"]:
        assert set(device.keys()) == {"deviceCode", "status", "metrics"}
    assert batch["teamCode"] == config.team_code
    assert batch["environment"] == config.environment
