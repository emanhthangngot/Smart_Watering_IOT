"""Bounded safety downgrade ladder from plan §7.3."""

from __future__ import annotations

LADDER = (
    "create_irrigation_schedule",
    "propose_irrigation_plan",
    "create_inspection_task",
)
MAX_DOWNGRADE_HOPS = 2


def downgrade_sequence(requested_tool: str) -> tuple[str, ...]:
    if requested_tool not in LADDER:
        return (requested_tool,)
    start = LADDER.index(requested_tool)
    return LADDER[start : start + MAX_DOWNGRADE_HOPS + 1]
