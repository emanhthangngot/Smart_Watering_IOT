"""store/outbox_drain.py — network resilience. plans/reports/plan.md §11.4,
plans/260816-0957-data-plane/phase-02-supabase-schema.md success criterion
3: "Simulated network failure writes to outbox, not lost; drain later
succeeds." No real Postgres required — the pool is monkeypatched so this
runs in CI.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import store.db
import store.ingest
import store.outbox_drain
from contracts import Reading


class _FakeConn:
    def __init__(self, fail: bool):
        self.fail = fail
        self.calls: list[str] = []

    async def execute(self, query, *args):
        self.calls.append(query)
        if self.fail:
            raise OSError("connection refused")


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, fail: bool):
        self._conn = _FakeConn(fail)

    def acquire(self):
        return _FakeAcquireCtx(self._conn)


@pytest.fixture(autouse=True)
def _reset_outbox(tmp_path, monkeypatch):
    outbox_file = tmp_path / "pending.jsonl"
    monkeypatch.setattr(store.outbox_drain, "OUTBOX_DIR", tmp_path)
    monkeypatch.setattr(store.outbox_drain, "OUTBOX_FILE", outbox_file)
    yield outbox_file


def _reading(device_code="TANK_01", metric="level", value=59.8, reading_id="r_abc123"):
    return Reading(
        reading_id=reading_id,
        device_code=device_code,
        metric=metric,
        value=value,
        unit="%",
        event_time="2026-08-16T02:36:56.000Z",
        received_at="2026-08-16T02:36:57.000Z",
        batch_epoch=1786847816,
        source_status="ok",
    )


@pytest.mark.data_plane
def test_network_failure_writes_to_outbox_not_lost(monkeypatch, _reset_outbox):
    fake_pool = _FakePool(fail=True)

    async def fake_get_pool(*a, **kw):
        return fake_pool

    monkeypatch.setattr(store.db, "get_pool", fake_get_pool)
    monkeypatch.setattr(store.ingest, "get_pool", fake_get_pool)

    written = asyncio.run(
        store.ingest.write_readings(
            [_reading()], epoch=1786847816, team_code="VAMOS", scenario="NORMAL", late=False
        )
    )

    assert written is False
    assert store.outbox_drain.outbox_depth() == 1
    lines = _reset_outbox.read_text().splitlines()
    payload = json.loads(lines[0])
    assert payload["epoch"] == 1786847816
    assert payload["eventTime"] == "2026-08-16T02:36:56.000Z"
    assert payload["devices"][0]["deviceCode"] == "TANK_01"
    assert payload["devices"][0]["id"] == "r_abc123"


@pytest.mark.data_plane
def test_drain_replays_outbox_in_order_and_empties_it(monkeypatch, _reset_outbox):
    store.outbox_drain.write_to_outbox({"epoch": 1, "devices": []})
    store.outbox_drain.write_to_outbox({"epoch": 2, "devices": []})
    assert store.outbox_drain.outbox_depth() == 2

    fake_pool = _FakePool(fail=False)

    async def fake_get_pool(*a, **kw):
        return fake_pool

    monkeypatch.setattr(store.outbox_drain, "get_pool", fake_get_pool)

    drained = asyncio.run(store.outbox_drain.drain_once())

    assert drained == 2
    assert store.outbox_drain.outbox_depth() == 0
    assert len(fake_pool._conn.calls) == 2


@pytest.mark.data_plane
def test_drain_stops_at_first_failure_preserving_order(monkeypatch, _reset_outbox):
    store.outbox_drain.write_to_outbox({"epoch": 1, "devices": []})
    store.outbox_drain.write_to_outbox({"epoch": 2, "devices": []})

    fake_pool = _FakePool(fail=True)

    async def fake_get_pool(*a, **kw):
        return fake_pool

    monkeypatch.setattr(store.outbox_drain, "get_pool", fake_get_pool)

    drained = asyncio.run(store.outbox_drain.drain_once())

    assert drained == 0
    assert store.outbox_drain.outbox_depth() == 2  # nothing lost, order preserved
