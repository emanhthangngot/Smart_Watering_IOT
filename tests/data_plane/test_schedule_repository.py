"""Live-Postgres tests for PostgresScheduleRepository (coordination gate C4):
durable schedule state and claim-vs-claim / claim-vs-add race safety across
processes, backed by the DB unique partial index, not an in-process lock.

Bring one up locally with:
    docker compose -f store/docker-compose.yml up -d --wait
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import psycopg2
import pytest

from schedule.claim import ScheduleConflict
from schedule.models import Schedule, ScheduleStatus
from store.schedule_repository import PostgresScheduleRepository, _dsn

pytestmark = pytest.mark.data_plane


def _repository() -> PostgresScheduleRepository:
    try:
        return PostgresScheduleRepository()
    except psycopg2.OperationalError as error:
        pytest.skip(f"no reachable Postgres for this test: {error}")


def _make_schedule(pump_id: str, *, status: ScheduleStatus = ScheduleStatus.PENDING) -> Schedule:
    now = datetime.now(UTC)
    return Schedule(
        schedule_id=f"sched_{uuid.uuid4().hex[:8]}",
        plan_revision_id=f"pr_{uuid.uuid4().hex[:8]}",
        pump_id=pump_id,
        start_at=now,
        end_at=now + timedelta(minutes=10),
        status=status,
        planned_drawdown_pct=5.0,
        planned_pump_minutes=10.0,
    )


def test_add_and_get_round_trip():
    repository = _repository()
    try:
        schedule = _make_schedule("PUMP_TEST_ADD")
        repository.add(schedule)
        fetched = repository.get(schedule.schedule_id)
        assert fetched is not None
        assert fetched.status is ScheduleStatus.PENDING
        assert fetched.pump_id == "PUMP_TEST_ADD"
    finally:
        repository.close()


def test_list_nonterminal_excludes_terminal_statuses():
    repository = _repository()
    try:
        live = _make_schedule("PUMP_TEST_LIST_1")
        done = _make_schedule("PUMP_TEST_LIST_2", status=ScheduleStatus.DONE)
        repository.add(live)
        repository.add(done)
        ids = {row.schedule_id for row in repository.list_nonterminal()}
        assert live.schedule_id in ids
        assert done.schedule_id not in ids
    finally:
        repository.close()


def test_two_concurrent_claims_exactly_one_wins_across_processes():
    repository = _repository()
    try:
        schedule = _make_schedule(f"PUMP_TEST_CLAIM_{uuid.uuid4().hex[:6]}")
        repository.add(schedule)

        def claim(worker_id: str) -> bool:
            # Separate connections, like separate worker processes would use.
            worker_repo = PostgresScheduleRepository()
            try:
                return worker_repo.try_claim(schedule.schedule_id, worker_id)
            finally:
                worker_repo.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ["worker-a", "worker-b"]))
        assert sum(results) == 1
        assert repository.get(schedule.schedule_id).status is ScheduleStatus.RUNNING
    finally:
        repository.close()


def test_running_pump_constraint_rejects_second_schedule_on_same_pump():
    repository = _repository()
    try:
        pump_id = f"PUMP_TEST_UNIQUE_{uuid.uuid4().hex[:6]}"
        first = _make_schedule(pump_id, status=ScheduleStatus.RUNNING)
        second = _make_schedule(pump_id, status=ScheduleStatus.RUNNING)
        repository.add(first)
        with pytest.raises(ScheduleConflict):
            repository.add(second)
    finally:
        repository.close()


def test_transition_only_succeeds_from_expected_status():
    repository = _repository()
    try:
        schedule = _make_schedule("PUMP_TEST_TRANSITION")
        repository.add(schedule)
        assert not repository.transition(
            schedule.schedule_id, expected={ScheduleStatus.RUNNING}, target=ScheduleStatus.DONE
        )
        assert repository.transition(
            schedule.schedule_id, expected={ScheduleStatus.PENDING}, target=ScheduleStatus.CANCELLED
        )
        assert repository.get(schedule.schedule_id).status is ScheduleStatus.CANCELLED
    finally:
        repository.close()


def test_dsn_falls_back_to_local_docker_default(monkeypatch):
    monkeypatch.delenv("LOCAL_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL_DIRECT", raising=False)
    from store.schedule_repository import DEFAULT_LOCAL_DSN

    assert _dsn() == DEFAULT_LOCAL_DSN
