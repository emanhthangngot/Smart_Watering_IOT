"""Central permission evaluation for every side-effecting tool."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from contracts import Approval, ToolPermission

Tier = Literal["AUTO", "PROPOSE", "INVESTIGATE"]
_TIER_RANK: dict[Tier, int] = {"INVESTIGATE": 0, "PROPOSE": 1, "AUTO": 2}


@dataclass(frozen=True)
class ToolContext:
    plan_revision_id: str
    revision_hash: str
    current_revision_hash: str
    plan_status: str
    tier: Tier
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    approval: Approval | None = None


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    code: str
    reason: str


class ToolStateStore(Protocol):
    """Authoritative state boundary; callers never supply their own safety state."""

    def get_context(self, plan_revision_id: str) -> ToolContext | None: ...

    def evidence_exists(self, evidence_ref: str) -> bool: ...


class InMemoryToolStateStore:
    """Thread-safe local adapter with defensive copies for tests and local mode."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contexts: dict[str, ToolContext] = {}
        self._evidence: set[str] = set()

    def put_context(self, context: ToolContext) -> None:
        with self._lock:
            self._contexts[context.plan_revision_id] = copy.deepcopy(context)

    def add_evidence(self, *evidence_refs: str) -> None:
        if any(not ref.strip() for ref in evidence_refs):
            raise ValueError("evidence references must be non-empty")
        with self._lock:
            self._evidence.update(evidence_refs)

    def get_context(self, plan_revision_id: str) -> ToolContext | None:
        with self._lock:
            context = self._contexts.get(plan_revision_id)
            return copy.deepcopy(context) if context is not None else None

    def evidence_exists(self, evidence_ref: str) -> bool:
        with self._lock:
            return evidence_ref in self._evidence


def evaluate_permission(
    permission: ToolPermission,
    context: ToolContext,
    *,
    now: datetime | None = None,
) -> PermissionDecision:
    """Fail closed; revision/evidence checks apply even without human approval."""

    now = now or datetime.now(UTC)
    if not context.plan_revision_id.strip() or not context.revision_hash.strip():
        return _deny("REVISION_INVALID", "plan revision id and hash are required")
    if not context.current_revision_hash.strip():
        return _deny("REVISION_INVALID", "authoritative current revision hash is required")
    if context.revision_hash != context.current_revision_hash:
        return _deny("REVISION_MISMATCH", "plan revision hash is stale or mismatched")
    if context.plan_status not in permission.allowed_plan_statuses:
        return _deny("PLAN_STATUS_DENIED", f"plan status {context.plan_status!r} is not allowed")
    if context.tier not in _TIER_RANK or permission.min_tier not in _TIER_RANK:
        return _deny("TIER_INVALID", "tier or tool tier policy is invalid")
    if _TIER_RANK[context.tier] < _TIER_RANK[permission.min_tier]:
        return _deny("TIER_DENIED", f"tier {context.tier} is below {permission.min_tier}")
    if not context.evidence_refs or any(not ref.strip() for ref in context.evidence_refs):
        return _deny("EVIDENCE_REQUIRED", "at least one grounded evidence reference is required")
    if not permission.approval_required:
        return PermissionDecision(True, "ALLOWED", "permission checks passed")

    approval = context.approval
    if approval is None:
        return _deny("APPROVAL_REQUIRED", "a valid approval is required")
    if approval.decision != "APPROVE":
        return _deny("APPROVAL_REJECTED", "the approval decision is not APPROVE")
    if approval.plan_revision_id != context.plan_revision_id:
        return _deny("APPROVAL_PLAN_MISMATCH", "approval belongs to another plan revision")
    if approval.revision_hash != context.revision_hash:
        return _deny("APPROVAL_HASH_MISMATCH", "approval does not match this revision hash")
    try:
        expires_at = _parse_time(approval.expires_at)
    except ValueError:
        return _deny("APPROVAL_INVALID", "approval expiry is not a valid timestamp")
    if expires_at <= now:
        return _deny("APPROVAL_EXPIRED", "approval has expired")
    return PermissionDecision(True, "ALLOWED", "permission and approval checks passed")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _deny(code: str, reason: str) -> PermissionDecision:
    return PermissionDecision(False, code, reason)
