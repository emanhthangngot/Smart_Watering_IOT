"""INV-3 adapter contract: one RUNNING schedule per pump.

The same invariant must also be present as a partial unique Postgres index in
M1's generated schema before G3 can close.
"""

from datetime import UTC, datetime, timedelta

import pytest

from schedule import InMemoryScheduleRepository, Schedule, ScheduleConflict, ScheduleStatus

pytestmark = pytest.mark.invariants


def test_repository_rejects_second_running_schedule_for_same_pump() -> None:
    now = datetime.now(UTC)
    repository = InMemoryScheduleRepository()
    repository.add(
        Schedule("s1", "p1", "PUMP_01", now, now + timedelta(minutes=5), ScheduleStatus.RUNNING)
    )
    with pytest.raises(ScheduleConflict):
        repository.add(
            Schedule(
                "s2",
                "p2",
                "PUMP_01",
                now,
                now + timedelta(minutes=5),
                ScheduleStatus.RUNNING,
            )
        )
