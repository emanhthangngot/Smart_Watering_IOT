"""Durable, Postgres-backed ScheduleRepository (coordination gate C4).

Implements schedule.claim.ScheduleRepository exactly, so ScheduleRunner can
take either this or InMemoryScheduleRepository with no other code change.
Uses psycopg2 (sync) rather than store/db.py's asyncpg pool: the Protocol's
methods are called synchronously from inside ScheduleRunner.tick(), which
itself runs inside an already-active asyncio loop (run_forever) — awaiting
an asyncpg call there would need a second event loop. A plain blocking
driver keeps the adapter simple and matches the runner's existing shape.

Claim safety does not rely on this process' lock: the schedules table has a
unique partial index (`schedules_one_running_per_pump`, one RUNNING row per
pump_id), so two workers can never both win a claim for the same pump even
across processes/restarts — psycopg2's IntegrityError on that constraint is
caught and turned into "claim did not win", not raised.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psycopg2
import psycopg2.errors
import psycopg2.extras

from schedule.claim import ScheduleConflict
from schedule.models import Schedule, ScheduleStatus

DSN_ENV = "LOCAL_POSTGRES_DSN"
DIRECT_DSN_ENV = "SUPABASE_DB_URL_DIRECT"
DEFAULT_LOCAL_DSN = "postgresql://farmops:farmops_dev@127.0.0.1:54322/farmops"

_COLUMNS = (
    "schedule_id",
    "plan_revision_id",
    "pump_id",
    "start_at",
    "end_at",
    "status",
    "claimed_by",
    "verification_result",
    "late_verification",
    "status_reason",
    "planned_drawdown_pct",
    "planned_pump_minutes",
    "closing_started_at",
    "closing_failure",
    "actuator_stopped",
    "verification_attempts",
)


def _dsn() -> str:
    return os.environ.get(DSN_ENV) or os.environ.get(DIRECT_DSN_ENV) or DEFAULT_LOCAL_DSN


def _row_to_schedule(row: dict) -> Schedule:
    return Schedule(
        schedule_id=row["schedule_id"],
        plan_revision_id=row["plan_revision_id"],
        pump_id=row["pump_id"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        status=ScheduleStatus(row["status"]),
        claimed_by=row["claimed_by"],
        verification_result=row["verification_result"],
        late_verification=row["late_verification"],
        status_reason=row["status_reason"],
        planned_drawdown_pct=row["planned_drawdown_pct"],
        planned_pump_minutes=row["planned_pump_minutes"],
        closing_started_at=row["closing_started_at"],
        closing_failure=row["closing_failure"],
        actuator_stopped=row["actuator_stopped"],
        verification_attempts=row["verification_attempts"],
    )


class PostgresScheduleRepository:
    """Durable adapter for ScheduleRepository. One connection per instance;
    safe to share across a single worker process (psycopg2 connections are
    not thread-safe for concurrent use, but ScheduleRunner.tick() is not
    re-entrant)."""

    def __init__(self, dsn: str | None = None) -> None:
        self._conn = psycopg2.connect(dsn or _dsn())
        self._conn.autocommit = True

    def close(self) -> None:
        self._conn.close()

    def add(self, schedule: Schedule) -> None:
        with self._conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    insert into schedules ({", ".join(_COLUMNS)})
                    values ({", ".join(f"%({c})s" for c in _COLUMNS)})
                    """,
                    {
                        "schedule_id": schedule.schedule_id,
                        "plan_revision_id": schedule.plan_revision_id,
                        "pump_id": schedule.pump_id,
                        "start_at": schedule.start_at,
                        "end_at": schedule.end_at,
                        "status": str(schedule.status),
                        "claimed_by": schedule.claimed_by,
                        "verification_result": schedule.verification_result,
                        "late_verification": schedule.late_verification,
                        "status_reason": schedule.status_reason,
                        "planned_drawdown_pct": schedule.planned_drawdown_pct,
                        "planned_pump_minutes": schedule.planned_pump_minutes,
                        "closing_started_at": schedule.closing_started_at,
                        "closing_failure": schedule.closing_failure,
                        "actuator_stopped": schedule.actuator_stopped,
                        "verification_attempts": schedule.verification_attempts,
                    },
                )
            except psycopg2.errors.UniqueViolation as error:
                if "schedules_pkey" in str(error):
                    raise ScheduleConflict(f"duplicate schedule: {schedule.schedule_id}") from error
                raise ScheduleConflict(f"pump already RUNNING: {schedule.pump_id}") from error

    def get(self, schedule_id: str) -> Schedule | None:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("select * from schedules where schedule_id = %s", (schedule_id,))
            row = cursor.fetchone()
        return _row_to_schedule(row) if row else None

    def list_nonterminal(self) -> list[Schedule]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                "select * from schedules where status not in "
                "('DONE', 'FAILED', 'MISSED', 'CANCELLED') order by schedule_id"
            )
            rows = cursor.fetchall()
        return [_row_to_schedule(row) for row in rows]

    def try_claim(self, schedule_id: str, worker_id: str) -> bool:
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    update schedules set status = 'RUNNING', claimed_by = %s
                    where schedule_id = %s and status = 'PENDING'
                    """,
                    (worker_id, schedule_id),
                )
                return cursor.rowcount == 1
        except psycopg2.errors.UniqueViolation:
            # Another worker already holds the one-RUNNING-per-pump slot.
            return False

    def transition(
        self,
        schedule_id: str,
        *,
        expected: set[ScheduleStatus],
        target: ScheduleStatus,
        reason: str | None = None,
    ) -> bool:
        expected_values = tuple(str(status) for status in expected)
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(
                    """
                    update schedules set status = %s, status_reason = %s
                    where schedule_id = %s and status = any(%s)
                    """,
                    (str(target), reason, schedule_id, list(expected_values)),
                )
                return cursor.rowcount == 1
        except psycopg2.errors.UniqueViolation:
            return False


class PostgresRecoveryQueries:
    """Startup recovery reads for api.recovery.RecoveryPort, backed by the
    same durable ``schedules``/``actions``/``approvals`` tables (C4)."""

    def __init__(self, dsn: str | None = None) -> None:
        self._conn = psycopg2.connect(dsn or _dsn())
        self._conn.autocommit = True

    def close(self) -> None:
        self._conn.close()

    def nonterminal_schedules(self) -> list[Schedule]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                "select * from schedules where status not in "
                "('DONE', 'FAILED', 'MISSED', 'CANCELLED') order by schedule_id"
            )
            rows = cursor.fetchall()
        return [_row_to_schedule(row) for row in rows]

    def pending_approvals(self) -> list[dict]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                "select * from approvals where expires_at is not null and expires_at > %s",
                (datetime.now(UTC),),
            )
            return list(cursor.fetchall())

    def pending_actions(self) -> list[dict]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("select * from actions where status not in ('DONE', 'FAILED')")
            return list(cursor.fetchall())


__all__ = ["PostgresRecoveryQueries", "PostgresScheduleRepository"]
