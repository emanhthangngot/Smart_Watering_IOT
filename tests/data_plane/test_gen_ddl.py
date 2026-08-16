"""store/gen_ddl.py — schema is generated from registry/specs.py, never
hand-edited. plans/reports/plan.md §11.4.
"""

from __future__ import annotations

import pytest

from registry.specs import DEVICES, SPECS
from store.gen_ddl import generate


@pytest.mark.data_plane
def test_generated_sql_has_do_not_hand_edit_header():
    sql = generate()
    assert "GENERATED FILE. DO NOT HAND-EDIT" in sql.splitlines()[0]


@pytest.mark.data_plane
def test_generated_sql_has_one_table_per_device():
    sql = generate()
    for device in DEVICES:
        assert f"create table {device.lower()}_readings" in sql


@pytest.mark.data_plane
def test_generated_sql_has_readings_all_view_covering_every_metric():
    sql = generate()
    assert "create view readings_all as" in sql
    for spec in SPECS:
        assert f"'{spec.device_code}' as device, '{spec.metric}' as metric" in sql


@pytest.mark.data_plane
def test_generated_sql_has_ingest_batch_rpc_and_stable_id_conflict_key():
    sql = generate()
    assert "create or replace function ingest_batch(payload jsonb)" in sql
    assert "unique (team_code, epoch)" not in sql
    assert sql.count("on conflict (id) do nothing") == len(DEVICES)
    assert sql.count("(team_code, epoch desc)") == len(DEVICES)
    assert "(payload->>'eventTime')::timestamptz" in sql
