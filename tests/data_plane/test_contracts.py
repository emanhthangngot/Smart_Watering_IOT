"""contracts.py additions for coordination gate C0: PlanRevision, PlanStatus,
canonical serializer, versioned revision-hash. plans/260816-0957-agents/plan.md.
"""

from __future__ import annotations

import pytest

from contracts import (
    REVISION_HASH_ALGORITHM_VERSION,
    PlanRevision,
    PlanStatus,
    compute_revision_hash,
    to_camel_case,
    to_snake_case,
)


def _revision(**overrides) -> PlanRevision:
    values = {
        "plan_revision_id": "pr_1",
        "plan_lineage_id": "pl_1",
        "version": 1,
        "status": PlanStatus.PROPOSED,
        "created_from_state_version": 7,
        "evidence_refs": ["r_abc#tank_level"],
    }
    values.update(overrides)
    return PlanRevision(**values)


@pytest.mark.data_plane
def test_plan_status_matches_vocabulary_already_used_in_api_and_schedule():
    assert {status.value for status in PlanStatus} == {
        "PROPOSED",
        "APPROVED",
        "EXECUTING",
        "SUSPENDED",
        "NEEDS_REPLAN",
        "EXPIRED",
        "REJECTED",
        "DONE",
        "CANCELLED",
    }


@pytest.mark.data_plane
def test_camel_snake_round_trip_is_stable():
    snake = {"plan_revision_id": "pr_1", "nested": {"created_from_state_version": 7}}
    camel = to_camel_case(snake)
    assert camel == {"planRevisionId": "pr_1", "nested": {"createdFromStateVersion": 7}}
    assert to_snake_case(camel) == snake


@pytest.mark.data_plane
def test_revision_hash_is_deterministic_and_versioned():
    first = compute_revision_hash(_revision())
    second = compute_revision_hash(_revision())
    assert first == second
    assert first.startswith(f"rh_{REVISION_HASH_ALGORITHM_VERSION}_")


@pytest.mark.data_plane
def test_revision_hash_changes_when_content_changes():
    base = compute_revision_hash(_revision())
    changed = compute_revision_hash(_revision(status=PlanStatus.APPROVED))
    assert base != changed


@pytest.mark.data_plane
def test_revision_hash_ignores_identity_and_audit_fields():
    a = compute_revision_hash(_revision(plan_revision_id="pr_1"))
    b = compute_revision_hash(_revision(plan_revision_id="pr_2"))
    assert a == b
