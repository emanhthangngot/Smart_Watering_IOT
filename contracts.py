"""Typed contracts shared across all FarmOps modules.

Design reference: plans/reports/plan.md §6.1 (assumption / plan record fields).

Ownership: seeded here by dev, filled in by M1 (feat/data-plane) at gate G0.
Once G0 freezes this file, changing a field requires bumping CONTRACT_VERSION
and announcing on dev — see plans/260816-0957-farmops-delivery/phase-02-contract-lock.md.

STATUS: stub. Not yet frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CONTRACT_VERSION = "0.0.0-unfrozen"


@dataclass(frozen=True)
class Reading:
    """One (device, metric) observation from a batch. §3.2."""

    reading_id: str
    device_code: str
    metric: str
    value: float
    unit: str
    event_time: str
    received_at: str
    batch_epoch: int
    source_status: str


@dataclass
class Assumption:
    """§6.1 assumption record. Filled by M1/M3."""

    assumption_id: str
    predicate: str
    status: Literal["VALID", "INVALIDATED"]
    evidence_refs: list[str] = field(default_factory=list)
    observation_window: str | None = None
    affected_action_ids: list[str] = field(default_factory=list)
    invalidated_at: str | None = None
    invalidated_reason: str | None = None
    invalidated_evidence: str | None = None


@dataclass
class Challenge:
    """§6.1 challenge record."""

    challenge_id: str
    target_plan_revision_id: str
    agent: str
    blocking: bool
    status: str
    reason: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Approval:
    """§6.1 approval record. §7.4: actor derived from operator token, not body."""

    approval_id: str
    plan_revision_id: str
    revision_hash: str
    approver: str
    decision: Literal["APPROVE", "REJECT"]
    timestamp: str
    expires_at: str
    comment: str | None = None


@dataclass
class ExpectedOutcome:
    """§6.1 expected outcome record."""

    metric: str
    predicate: str
    threshold: float
    tolerance: float
    observation_window: str
    evidence_source: str
    affected_assumption_id: str


@dataclass
class Verification:
    """§10.1 verification record. INCONCLUSIVE is never PASS."""

    layer: Literal["ACTION", "OUTCOME"]
    expected: Any
    observed: Any
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    window: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class ToolPermission:
    """§6.1 tool permission record. Enforced by tools/ (M4), never bypassed."""

    tool: str
    allowed_plan_statuses: list[str]
    min_tier: Literal["AUTO", "PROPOSE", "INVESTIGATE"]
    approval_required: bool
    idempotency_key_formula: str
