"""Typed contracts shared across all FarmOps modules.

Design reference: plans/reports/plan.md §6.1 (assumption / plan record fields).

Ownership: frozen by M1 (feat/data-plane) at gate G0. Changing a field
after freeze requires bumping CONTRACT_VERSION and announcing on dev — see
plans/260816-0957-farmops-delivery/phase-02-contract-lock.md.

STATUS: frozen at G0. CONTRACT_VERSION bumped to 1.1.0 (additive only —
PlanRevision, PlanStatus, the canonical serializer, and the revision-hash
algorithm were added; no existing field was renamed or removed) to close
coordination gate C0 for M3 (feat/agents). See
plans/260816-0957-agents/plan.md §Coordination Ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from typing import Any, Literal

CONTRACT_VERSION = "1.1.0"


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
    requested_evidence: list[str] = field(default_factory=list)
    requested_revision: str | None = None


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


class PlanStatus(StrEnum):
    """Plan revision lifecycle. Values match the strings already in use
    across api/service.py, api/recovery.py, and schedule/runner.py; this
    enum makes that vocabulary a single frozen source instead of scattered
    string literals."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUSPENDED = "SUSPENDED"
    NEEDS_REPLAN = "NEEDS_REPLAN"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


@dataclass
class PlanRevision:
    """§6.1 plan revision record; mirrors store/schema.sql plan_revisions.

    Field order and names track the DB columns 1:1 so a row can round-trip
    through ``asdict()``/``**row`` without a translation layer.
    """

    plan_revision_id: str
    plan_lineage_id: str
    version: int
    status: PlanStatus | str
    created_from_state_version: int
    revision_of_plan_revision_id: str | None = None
    goal: dict[str, Any] | None = None
    evidence_refs: list[str] = field(default_factory=list)
    constraints: dict[str, Any] | None = None
    assumptions: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    expected_outcomes: list[dict[str, Any]] = field(default_factory=list)
    water_budget: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None
    requires_approval: bool = False
    challenges: list[str] = field(default_factory=list)
    decision_log: list[dict[str, Any]] = field(default_factory=list)


_CAMEL_BOUNDARY = re.compile(r"_([a-z0-9])")
_SNAKE_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def to_camel_case(value: Any) -> Any:
    """Recursively convert dict/list snake_case keys to camelCase. Non-dict/
    list leaves pass through unchanged; this is the wire-format direction."""
    if isinstance(value, dict):
        return {
            _CAMEL_BOUNDARY.sub(lambda m: m.group(1).upper(), key): to_camel_case(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [to_camel_case(item) for item in value]
    return value


def to_snake_case(value: Any) -> Any:
    """Recursively convert dict/list camelCase keys to snake_case. Inverse
    of ``to_camel_case``; this is the storage/Python-attribute direction."""
    if isinstance(value, dict):
        return {
            _SNAKE_BOUNDARY.sub("_", key).lower(): to_snake_case(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [to_snake_case(item) for item in value]
    return value


REVISION_HASH_ALGORITHM_VERSION = 1

# Fields excluded from the hash because they are set after the content that
# matters to an approver already exists (server-assigned identity/audit
# fields, not plan content).
_REVISION_HASH_EXCLUDED_FIELDS = frozenset({"plan_revision_id", "created_at"})


def compute_revision_hash(plan_revision: PlanRevision | dict[str, Any]) -> str:
    """Deterministic, versioned hash of a plan revision's content.

    An approval binds to this hash (contracts.py ``Approval.revision_hash``);
    changing any hashed field after approval must produce a different hash so
    a stale approval can never be replayed against revised plan content.
    """
    payload = asdict(plan_revision) if is_dataclass(plan_revision) else dict(plan_revision)
    hashed = {
        key: value for key, value in payload.items() if key not in _REVISION_HASH_EXCLUDED_FIELDS
    }
    canonical = json.dumps(
        to_camel_case(hashed),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"rh_{REVISION_HASH_ALGORITHM_VERSION}_{digest}"
